import torch
import torch.nn as nn
import torch.nn.functional as F

from .utils import get_img_coordinates


class FullyConnected(nn.Module):

    def __init__(self, in_features: int, out_features: int, activation=None):
        super().__init__()
        self.linear = nn.Linear(in_features=in_features, out_features=out_features)
        self.activation = activation

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _y = self.linear(x)
        if self.activation is not None:
            _y = self.activation(_y)
        return _y


class BatchNormConv2D(nn.Module):

    def __init__(self, in_channels: int, out_channels: int, activation=None, **args):
        super().__init__()
        self.conv2d = nn.Conv2d(in_channels=in_channels, out_channels=out_channels, **args)
        self.batch_norm = nn.BatchNorm2d(num_features=out_channels, eps=1e-3)
        self.activation = activation

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _y = self.conv2d(x)
        _y = self.batch_norm(_y)
        if self.activation is not None:
            _y = self.activation(_y)
        return _y


class SpatialSoftArgmax(nn.Module):

    def __init__(self,
                 temperature: float = None,
                 normalize: bool = False):
        """ Creates class instance.

        :param temperature: Temperature parameter (see paper)
        :param normalize: Set true to normalize spatial features to [-1, 1]
        """
        super().__init__()

        self.temperature = nn.Parameter(torch.ones(1) if temperature is None else torch.tensor([temperature]))
        self.normalize = normalize
        # self.spatial_softmax = nn.Softmax2d()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """ Apply Spatial Soft ArgMax to the input tensor.

        :param x: (Batch) input of image(s) in (N, C, H, W) format.
        :return: Spatial features (one point per channel) in (N, C, 2) format.
        """
        n, c, h, w = x.size()

        spatial_softmax = F.softmax(x.view(n*c, h*w)/self.temperature, dim=1).view(n, c, h, w)

        # Get img. coordinate maps
        img_x, img_y = get_img_coordinates(h=h, w=w, normalize=self.normalize)

        img_coordinates = torch.cat((img_x.unsqueeze(-1), img_y.unsqueeze(-1)), dim=-1).to(x.device)

        # Multiply coordinates by softmax and sum over height and width
        spatial_soft_argmax = torch.sum(spatial_softmax.unsqueeze(-1) * img_coordinates.unsqueeze(0), dim=[2, 3])

        assert spatial_soft_argmax.size() == (n, c, 2)

        return spatial_soft_argmax


