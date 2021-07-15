import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset
import numpy as np

from src.models.ulosd import ULOSD, ULOSD_Parallel
from src.models.inception3 import CustomInception3
from src.models.utils import load_inception_weights
from src.losses import temporal_separation_loss, inception_encoding_loss
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

        self.inception_net = CustomInception3().to(self.device)
        load_inception_weights(self.inception_net, config)

        if config['multi_gpu'] is True and torch.cuda.device_count() >= 1:
            self.model = ULOSD_Parallel(self.model)
            self.model.to(self.device)

        # self.reset_optim_and_scheduler(config=config)

        # Logged values
        self.rec_loss_per_iter = []
        self.sep_loss_per_iter = []
        self.l1_penalty_per_iter = []
        self.l2_reg_per_iter = []
        self.total_loss_per_iter = []

    def preprocess(self, x: torch.Tensor, config: dict) -> (torch.Tensor, (torch.Tensor, torch.Tensor)):
        """ Maps the input image sequence to range (-0.5, 0.5).
            Then returns input as input and target for reconstruction.

            NOTE: MIME data should already be in (0, 1).

        :param x: Image sequence in (N, T, C, H, W)
        :param config:
        :return:
        """
        assert x.max() <= 1
        assert x.min() >= 0
        x = x - 0.5
        return x, x

    """
    def loss_func(self, prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        ''' Normalized L2 loss (MSE) for image reconstruction

            NOTE: PyTorch already averages across the first dimension by default (N).

        :param prediction: Sequence of predicted images in (N, T, C, H, W)
        :param target: Actual image sequence in (N, T, C, H, W)
        :return: Normalized L2 loss between prediction and target
        '''
        N, T = target.shape[0], target.shape[1]
        loss = F.mse_loss(input=prediction.view((N*T, *tuple(target.shape[2:]))),
                          target=target.view((N*T, *tuple(target.shape[2:]))))
        # loss /= (N*T)
        return loss
    """

    def loss_func(self, prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return inception_encoding_loss(inception_net=self.inception_net,
                                       prediction=prediction,
                                       target=target)

    def separation_loss(self, keypoint_coordinates: torch.Tensor, config: dict) -> torch.Tensor:
        return temporal_separation_loss(cfg=config, coords=keypoint_coordinates)

    def l1_activation_penalty(self, feature_maps: torch.Tensor, config: dict) -> torch.Tensor:
        # return config['model']['feature_map_regularization'] * torch.norm(feature_maps, p=1)
        feature_map_mean = torch.mean(feature_maps, dim=[-2, -1])
        penalty = torch.mean(torch.abs(feature_map_mean))
        return config['model']['feature_map_regularization'] * penalty

    def key_point_sparsity_loss(self, keypoint_coordinates: torch.Tensor, config: dict) -> torch.Tensor:
        key_point_scales = keypoint_coordinates[..., 2]
        loss = torch.mean(torch.sum(torch.abs(key_point_scales), dim=2), dim=[0, 1])
        return config['model']['feature_map_regularization'] * loss

    def l2_kernel_regularization(self, config: dict) -> torch.Tensor:

        l2_reg = None

        for p_name, param in self.model.named_parameters():
            if ".weight" in p_name:
                if l2_reg is None:
                    l2_reg = param.norm(2)**2
                else:
                    l2_reg += param.norm(2)**2

        return config['training']['l2_kernel_reg_lambda'] * l2_reg

    def reset_logged_values(self):
        super(ULOSD_Agent, self).reset_logged_values()
        self.rec_loss_per_iter = []
        self.sep_loss_per_iter = []
        self.l1_penalty_per_iter = []
        self.l2_reg_per_iter = []
        self.total_loss_per_iter = []

    def log_values(self, fold: int, epoch: int, epochs_per_fold: int):
        global_epoch = fold*epochs_per_fold + epoch
        avg_reconstruction_loss = np.mean(self.rec_loss_per_iter)
        avg_separation_loss = np.mean(self.sep_loss_per_iter)
        avg_l1_penalty = np.mean(self.l1_penalty_per_iter)
        avg_l2_regularization = np.mean(self.l2_reg_per_iter)
        avg_total_loss = np.mean(self.total_loss_per_iter)
        self.writer.add_scalar(tag="train/reconstruction_loss",
                               scalar_value=avg_reconstruction_loss, global_step=global_epoch)
        self.writer.add_scalar(tag="train/separation_loss",
                               scalar_value=avg_separation_loss, global_step=global_epoch)
        self.writer.add_scalar(tag="train/l1_activation_penalty",
                               scalar_value=avg_l1_penalty, global_step=global_epoch)
        self.writer.add_scalar(tag="train/l2_kernel_regularization",
                               scalar_value=avg_l2_regularization, global_step=global_epoch)
        self.writer.add_scalar(tag="train/total_loss",
                               scalar_value=avg_total_loss, global_step=global_epoch)

    def reset_optim_and_scheduler(self, config: dict):

        self.optim = torch.optim.Adam(
            params=self.model.parameters(),
            lr=config['training']['initial_lr']
        )

        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer=self.optim,
            T_max=config['training']['epochs'],
            eta_min=config['training']['min_lr']
        )

    def train_step(self, sample: torch.Tensor, target: torch.Tensor, config: dict) -> torch.Tensor:
        """ One step of training.

        :param sample: Image sequence in (N, T, C, H, W)
        :param target: -
        :param config: Configuration dictionary
        :return: TODO
        """
        self.optim.zero_grad()

        sample, target = sample.to(self.device), target.to(self.device)

        # Vision model
        feature_maps, observed_key_points = self.model.encode(sample)
        reconstructed_images = self.model.decode(observed_key_points, sample[:, 0, ...].unsqueeze(1))
        reconstructed_images = torch.clip(reconstructed_images, -0.5, 0.5)

        # Dynamics model
        # TODO: Not used yet

        # Losses
        reconstruction_loss = self.loss_func(prediction=reconstructed_images,
                                             target=sample)
        self.rec_loss_per_iter.append(reconstruction_loss.detach().cpu().numpy())

        separation_loss = self.separation_loss(keypoint_coordinates=observed_key_points, config=config)
        separation_loss_scale = config['training']['separation_loss_scale']
        separation_loss *= separation_loss_scale
        self.sep_loss_per_iter.append(separation_loss.detach().cpu().numpy())

        # feature-map (L1) regularization of the activations of the last layer
        # l1_penalty = self.l1_activation_penalty(feature_maps=feature_maps, config=config)
        l1_penalty = self.key_point_sparsity_loss(keypoint_coordinates=observed_key_points, config=config)
        self.l1_penalty_per_iter.append(l1_penalty.detach().cpu().numpy())

        l2_kernel_reg = self.l2_kernel_regularization(config=config)
        self.l2_reg_per_iter.append(l2_kernel_reg.detach().cpu().numpy())

        # TODO: Not used yet
        coord_pred_loss = 0
        kl_loss = 0
        kl_loss_scale = 0
        kl_loss *= kl_loss_scale

        L = reconstruction_loss + separation_loss + l1_penalty + l2_kernel_reg \
            + coord_pred_loss + kl_loss
        self.total_loss_per_iter.append(L.detach().cpu().numpy())

        L.backward()

        # Clip gradient norm
        nn.utils.clip_grad_norm_(self.model.parameters(), config['training']['clip_norm'])

        self.optim.step()

        return L

    def validation_loss(self,
                        sample: torch.Tensor,
                        prediction: torch.Tensor,
                        target: torch.Tensor,
                        config: dict) -> torch.Tensor:

        """ Returns the total loss of the vision part."""

        feature_maps, observed_key_points = self.model.encode(sample)
        reconstructed_images = self.model.decode(observed_key_points, sample[:, 0, ...].unsqueeze(1))
        reconstructed_images = torch.clip(reconstructed_images, -0.5, 0.5)

        # Dynamics model
        # TODO: Not used yet

        # Losses
        reconstruction_loss = self.loss_func(prediction=reconstructed_images,
                                             target=sample)

        separation_loss = self.separation_loss(keypoint_coordinates=observed_key_points, config=config)
        separation_loss_scale = config['training']['separation_loss_scale']
        separation_loss *= separation_loss_scale

        # feature-map (L1) regularization of the activations of the last layer
        l1_penalty = self.l1_activation_penalty(feature_maps=feature_maps, config=config)

        l2_kernel_reg = self.l2_kernel_regularization(config=config)

        # TODO: Not used yet
        coord_pred_loss = 0
        kl_loss = 0
        kl_loss_scale = 0
        kl_loss *= kl_loss_scale

        L = reconstruction_loss + separation_loss + l1_penalty + l2_kernel_reg \
            + coord_pred_loss + kl_loss

        return L
