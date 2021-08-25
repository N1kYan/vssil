import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from cv2 import VideoWriter, VideoWriter_fourcc


class NPZ_Dataset(Dataset):
    """ Dataset class with data loaded from a .npz file."""

    def __init__(self,
                 num_timesteps: int,
                 root_path: str,
                 key_word: str):
        super(NPZ_Dataset, self).__init__()

        self.data = torch.tensor(read_npz_data(root_path)[key_word])
        self.num_timesteps = num_timesteps

    def __len__(self):
        return len(self.data) - self.num_timesteps

    def __getitem__(self, index):
        #float_img_tensor = torch.tensor(data=(self.data[index:index+self.num_timesteps]/255).clone().detach(),
        #                                dtype=torch.float32)
        float_img_tensor = torch.FloatTensor(self.data[index:index+self.num_timesteps]/255)
        return float_img_tensor, torch.empty([])


def read_npz_data(path: str):
    npz_file = np.load(path)

    np_images = npz_file['image'].transpose(0, 3, 1, 2)
    np_actions = npz_file['action']
    np_rewards = npz_file['reward']
    np_orientations = npz_file['orientations']
    np_velocities = npz_file['velocity']
    return {
        'images': np_images,
        'actions': np_actions,
        'rewards': np_rewards,
        'orientations': np_orientations,
        'velocities': np_velocities
    }


def nump_to_mp4(img_array: np.ndarray, target_path: str = 'test.avi'):
    width = 64
    height = 64
    fps = 25
    assert img_array.shape[0] % fps == 0
    sec = int(img_array.shape[0]/fps)
    fourcc = VideoWriter_fourcc(*'MPEG')
    video = VideoWriter(target_path, fourcc, float(fps), (width, height))
    for frame_count in range(fps*sec):
        video.write(img_array[frame_count, ...])
    video.release()


if __name__ == "__main__":
    npz_data_set = NPZ_Dataset(
        num_timesteps=8,
        root_path='/home/yannik/vssil/video_structure/testdata/acrobot_swingup_random_repeat40_00006887be28ecb8.npz',
        key_word='images')

    data_loader = DataLoader(dataset=npz_data_set, batch_size=32, shuffle=False)
    print(f'Read {len(npz_data_set)} samples.')
    for i, (sample, label) in enumerate(data_loader):
        print(sample.mean())
        # nump_to_mp4(img_array=sample.permute(0, 2, 3, 1).cpu().numpy())
        exit()