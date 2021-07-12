import yaml
import argparse

import torch
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt

from src.data.utils import combine_mime_hd_kinect_tasks
from src.agents.ulosd_agent import ULOSD_Agent
from src.data.utils import play_video
from src.utils.feature_visualization import make_annotated_tensor

parser = argparse.ArgumentParser()
parser.add_argument('config_path', metavar='CP', type=str, help='Path to config file.')
parser.add_argument('data_path', metavar='DP', type=str, help='Base path to dataset.')
args = parser.parse_args()

with open(args.config_path, 'r') as stream:
    ulosd_conf = yaml.safe_load(stream)
    ulosd_conf['device'] = 'cpu'
    ulosd_conf['data']['tasks'] = ['pull_one_hand']

data_set = combine_mime_hd_kinect_tasks(
    task_list=ulosd_conf['data']['tasks'],
    base_path=args.data_path,
    # timesteps_per_sample=ulosd_conf['model']['n_frames'],
    timesteps_per_sample=-1,
    overlap=ulosd_conf['data']['overlap'],
    img_shape=eval(ulosd_conf['data']['img_shape'])
)

eval_data_loader = DataLoader(
    dataset=data_set,
    batch_size=1,
    shuffle=True
)

ulosd_agent = ULOSD_Agent(dataset=data_set,
                          config=ulosd_conf)

ulosd_agent.eval_data_loader = eval_data_loader
ulosd_agent.load_checkpoint("/home/yannik/ulosd_checkpoint.PTH")
# ulosd_agent.load_checkpoint("/home/yannik/vssil/results/ulosd/2021_7_11_14_49/checkpoints/chckpt_e60.PTH")

with torch.no_grad():
    for i, sample in enumerate(eval_data_loader):
        sample, _ = ulosd_agent.preprocess(sample, ulosd_conf)

        feature_maps, key_points = ulosd_agent.model.encode(image_sequence=sample)

        print(key_points)

        reconstruction = ulosd_agent.model(sample)
        annotated_reconstruction = make_annotated_tensor(image_series=reconstruction[0, ...],
                                                         feature_positions=key_points[0, ...])
        annotated_sample = make_annotated_tensor(image_series=sample[0, ...],
                                                 feature_positions=key_points[0, ...])

        print(reconstruction.min())
        print(reconstruction.max())

        rec_loss = ulosd_agent.loss_func(prediction=reconstruction, target=sample)

        sep_loss = ulosd_agent.separation_loss(keypoint_coordinates=key_points, config=ulosd_conf)

        l1_penalty = ulosd_agent.l1_activation_penalty(feature_maps=feature_maps, config=ulosd_conf)

        l2_kernel_reg = ulosd_agent.l2_kernel_regularization(config=ulosd_conf)

        print(f"Sample {i}\t Rec. loss: {rec_loss}\t Sep. loss: {sep_loss}\t L1 penalty: {l1_penalty}\t "
              f"L2 reg: {l2_kernel_reg}")

        np_samples = sample[0, ...].cpu().numpy().transpose(0, 2, 3, 1) + 0.5
        np_recs = reconstruction[0, ...].cpu().numpy().transpose(0, 2, 3, 1) + 0.5
        # play_video(sample[0, ...])
        # play_video(reconstruction[0, ...])
        play_video(annotated_reconstruction)
        fig, ax = plt.subplots(2, 1)
        ax[0].imshow(np_samples[0, ...])
        ax[1].imshow(np_recs[0, ...])
        plt.show()
        if i == 0:
            exit()

# ulosd_agent.evaluate(config=ulosd_conf)
