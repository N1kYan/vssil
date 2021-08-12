import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset
import numpy as np

from src.models.ulosd import ULOSD, ULOSD_Parallel, ULOSD_Dist_Parallel
from src.models.inception3 import CustomInception3
from src.models.utils import load_inception_weights
from src.losses import temporal_separation_loss, inception_encoding_loss
from src.utils.grad_flow import plot_grad_flow
from src.utils.visualization import gen_eval_imgs
from .abstract_agent import AbstractAgent


class ULOSD_Agent(AbstractAgent):

    def __init__(self,
                 dataset: Dataset,
                 config: dict
                 ):
        """ Creates class instance.

        :param dataset: Dataset to use for training and validation
        :param config: Dictionary of parameters
        """
        super(ULOSD_Agent, self).__init__(
            name="ULOSD Agent",
            dataset=dataset,
            config=config
        )

        # Input shape
        N = config['training']['batch_size']
        T = config['model']['n_frames']
        C = 3
        H = eval(config['data']['img_shape'])[0]
        W = eval(config['data']['img_shape'])[1]
        input_shape = (T, C, H, W)

        self.model = ULOSD(
            input_shape=input_shape,
            config=config
        ).to(self.device)

        if config['training']['reconstruction_loss'] in ['inception', 'Inception', 'INCEPTION']:
            self.inception_net = CustomInception3().to(self.device)
            load_inception_weights(self.inception_net, config)

        if config['multi_gpu'] is True and torch.cuda.device_count() >= 1:
            # self.model = ULOSD_Dist_Parallel(
            self.model = ULOSD_Parallel(
                module=self.model,
                device_ids=list(range(torch.cuda.device_count())),
                dim=0
            )
            # self.model = ULOSD_Parallel(self.model)
            # TODO: Is the next line required?
            self.model.to(self.device)

        # Logged values
        self.rec_loss_per_iter = []
        self.sep_loss_per_iter = []
        self.l1_penalty_per_iter = []
        self.total_loss_per_iter = []

    def preprocess(self,
                   x: torch.Tensor,
                   label: torch.Tensor,
                   config: dict) -> (torch.Tensor, (torch.Tensor, torch.Tensor)):
        """ Maps the input image sequence to range (-0.5, 0.5).
            Then returns input as input and target for reconstruction.

            NOTE: MIME data should already be in (0, 1).

        :param x: Image sequence in (N, T, C, H, W)
        :param label: Label sequence in (N, T, K)
        :param config:
        :return:
        """
        assert x.max() <= 1
        assert x.min() >= 0
        x = x - 0.5
        return x, torch.empty([])

    def loss_func(self,
                  prediction: torch.Tensor,
                  target: torch.Tensor,
                  config: dict) -> torch.Tensor:
        """ Loss for image reconstruction.

            Either uses the (normalized) L2 MSE as in
            ...TODO
            or passes the original image and the reconstruction trough a port
            of a pretrained inception net and calculates the loss on that encoding
            as in
            ...TODO

            NOTE: PyTorch already averages across the first dimension by default (N).

        :param prediction: Sequence of predicted images in (N, T, C, H, W)
        :param target: Actual image sequence in (N, T, C, H, W)
        :param config: Config dictionary
        :return: Reconstruction loss between prediction and target
        """
        rec_loss = config['training']['reconstruction_loss']
        assert rec_loss in ['mse', 'MSE', 'Inception', 'inception']

        loss = None

        if rec_loss in ['mse', 'MSE']:
            N, T = target.shape[0], target.shape[1]
            loss = F.mse_loss(input=prediction.view((N * T, *tuple(target.shape[2:]))),
                              target=target.view((N * T, *tuple(target.shape[2:]))),
                              reduction='sum')
            # loss /= (N*T)

        if rec_loss in ['Inception', 'inception', 'INCEPTION']:
            loss = inception_encoding_loss(inception_net=self.inception_net,
                                           prediction=prediction,
                                           target=target)

        return loss

    def separation_loss(self, keypoint_coordinates: torch.Tensor, config: dict) -> torch.Tensor:
        separation_loss_scale = config['training']['separation_loss_scale']
        return temporal_separation_loss(cfg=config, coords=keypoint_coordinates) * separation_loss_scale

    def l1_activation_penalty(self, feature_maps: torch.Tensor, config: dict) -> torch.Tensor:
        # return config['model']['feature_map_regularization'] * torch.norm(feature_maps, p=1)
        feature_map_mean = torch.mean(feature_maps, dim=[-2, -1])
        penalty = torch.mean(torch.abs(feature_map_mean))
        return config['training']['feature_map_regularization'] * penalty

    def key_point_sparsity_loss(self, keypoint_coordinates: torch.Tensor, config: dict) -> torch.Tensor:
        key_point_scales = keypoint_coordinates[..., 2]
        loss = torch.mean(torch.sum(torch.abs(key_point_scales), dim=2), dim=[0, 1])
        return config['training']['feature_map_regularization'] * loss

    def l2_kernel_regularization(self, config: dict) -> torch.Tensor:
        """ TODO: This is replaced by PyTorch's weight decay in the optimizer. """
        l2_reg = None

        for p_name, param in self.model.named_parameters():
            if ".weight" in p_name:
                if l2_reg is None:
                    l2_reg = param.norm(2) ** 2
                else:
                    l2_reg += param.norm(2) ** 2

        return config['training']['l2_kernel_reg_lambda'] * l2_reg

    def reset_logged_values(self):
        super(ULOSD_Agent, self).reset_logged_values()
        self.rec_loss_per_iter = []
        self.sep_loss_per_iter = []
        self.l1_penalty_per_iter = []
        self.total_loss_per_iter = []

    def log_values(self, fold: int, epoch: int, epochs_per_fold: int):
        global_epoch = fold * epochs_per_fold + epoch
        avg_reconstruction_loss = np.mean(self.rec_loss_per_iter)
        avg_separation_loss = np.mean(self.sep_loss_per_iter)
        avg_l1_penalty = np.mean(self.l1_penalty_per_iter)
        avg_total_loss = np.mean(self.total_loss_per_iter)
        self.writer.add_scalar(tag="train/reconstruction_loss",
                               scalar_value=avg_reconstruction_loss, global_step=global_epoch)
        self.writer.add_scalar(tag="train/separation_loss",
                               scalar_value=avg_separation_loss, global_step=global_epoch)
        self.writer.add_scalar(tag="train/l1_activation_penalty",
                               scalar_value=avg_l1_penalty, global_step=global_epoch)
        self.writer.add_scalar(tag="train/total_loss",
                               scalar_value=avg_total_loss, global_step=global_epoch)

    def step(self,
             sample: torch.Tensor,
             target: torch.Tensor,
             global_epoch_number: int,
             save_grad_flow_plot: bool,
             save_val_sample: bool,
             config: dict,
             mode: str) -> torch.Tensor:
        """ One step of training.

        :param sample: Image sequence in (N, T, C, H, W)
        :param target: -
        :param global_epoch_number: Number of global epochs
        :param save_grad_flow_plot: Whether or not to plot the gradient flow
        :param save_val_sample: Set true to save a sample video during validation
        :param config: Configuration dictionary
        :param mode: Flag to determine 'training' or 'validation' mode
        :return: Total loss
        """

        assert mode in ['training', 'validation']

        if mode == 'training':
            self.optim.zero_grad()

        # Vision model
        feature_maps, observed_key_points = self.model.encode(sample)
        reconstructed_diff = self.model.decode(observed_key_points, sample[:, 0, ...].unsqueeze(1))

        # NOTE: Clipping the prediction to (-1, 1) bcs. it is the predicted diff. between v_t and v_1
        reconstructed_diff = torch.clip(reconstructed_diff, -1.0, 1.0)

        # Dynamics model
        # TODO: Not used yet

        # Losses
        target_diff = sample - sample[:, 0, ...].unsqueeze(1)
        reconstruction_loss = self.loss_func(prediction=reconstructed_diff,
                                             target=target_diff,
                                             config=config)

        separation_loss = self.separation_loss(keypoint_coordinates=observed_key_points,
                                               config=config)

        # feature-map (L1) regularization of the activations of the last layer
        l1_penalty = self.l1_activation_penalty(feature_maps=feature_maps,
                                                config=config)
        # l1_penalty = self.key_point_sparsity_loss(keypoint_coordinates=observed_key_points, config=config)

        # TODO: Losses for the dynamics model, not used yet
        coord_pred_loss = 0
        kl_loss = 0
        kl_loss_scale = 0
        kl_loss *= kl_loss_scale

        # total loss
        L = reconstruction_loss + separation_loss + l1_penalty + coord_pred_loss + kl_loss
        # L = reconstruction_loss

        if mode == 'validation' and config['validation']['save_video']:
            with torch.no_grad():
                torch_img_series_tensor = gen_eval_imgs(sample=sample,
                                                        reconstruction=reconstructed_diff,
                                                        key_points=observed_key_points)
                # reconstructed_image_series_tensor = reconstructed_diff + sample[:, 0, ...].unsqueeze(1)
                # self.writer.add_video(tag='val/reconstruction_sample',
                #                       vid_tensor=reconstructed_image_series_tensor[0, ...].detach(),
                #                       global_step=global_epoch_number)
                self.writer.add_video(tag='val/reconstruction_sample',
                                      vid_tensor=torch_img_series_tensor,
                                      global_step=global_epoch_number)
                self.writer.flush()

        # Log values and backprop. during training
        if mode == 'training':
            self.rec_loss_per_iter.append(reconstruction_loss.detach().cpu().numpy())
            self.sep_loss_per_iter.append(separation_loss.detach().cpu().numpy())
            self.l1_penalty_per_iter.append(l1_penalty.detach().cpu().numpy())
            self.total_loss_per_iter.append(L.detach().cpu().numpy())

            L.backward()

            # Clip gradient norm
            nn.utils.clip_grad_norm_(self.model.parameters(), config['training']['clip_norm'])

            with torch.no_grad():
                if save_grad_flow_plot:
                    plot_grad_flow(named_parameters=self.model.encoder.named_parameters(),
                                   epoch=global_epoch_number,
                                   summary_writer=self.writer,
                                   tag_name='encoder')
                    plot_grad_flow(named_parameters=self.model.appearance_net.named_parameters(),
                                   epoch=global_epoch_number,
                                   summary_writer=self.writer,
                                   tag_name='appearance_net')
                    plot_grad_flow(named_parameters=self.model.decoder.named_parameters(),
                                   epoch=global_epoch_number,
                                   summary_writer=self.writer,
                                   tag_name='decoder')
                    self.writer.flush()

            self.optim.step()

        return L
