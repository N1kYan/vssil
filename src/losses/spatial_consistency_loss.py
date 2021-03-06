import numpy as np
import torch


def spatial_consistency_loss(keypoint_coordinates: torch.Tensor) -> torch.Tensor:
    """ Encourages key-points to have small - or more consistent - spatial movement
        across time-steps, by penalizing a high coefficient of variation in the positional differences.

    :param keypoint_coordinates: Torch tensor of key-point coordinates in (N, T, C, 2/3)
    :param cfg: Additional configuration dictionary
    :return: The consistency loss
    """

    assert keypoint_coordinates.dim() == 4

    N, T, K, D = keypoint_coordinates.shape

    diff_tensor = torch.zeros(N, T - 1, K).to(keypoint_coordinates.device)

    for t in np.arange(1, keypoint_coordinates.shape[1]):
        # NOTE: The difference between intensity values is not considered
        diff_tensor[:, t - 1, :] = torch.norm(keypoint_coordinates[:, t, :, :2] - keypoint_coordinates[:, t - 1, :, :2],
                                              p=1, dim=-1)

    # Average diff across time
    diff_mean = torch.mean(diff_tensor, dim=1) + 1e-6  # (N, K)
    diff_std = torch.std(diff_tensor, dim=1)  # (N, K)

    # Coefficient of variation
    coeff = torch.div(diff_std, torch.abs(diff_mean) + 1)  # (N, K)

    # Average across batch and key-points
    L = torch.mean(coeff)

    return L
