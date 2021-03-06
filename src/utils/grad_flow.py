import torch
import numpy as np
import matplotlib.pyplot as plt
from torch.utils.tensorboard import SummaryWriter


def pyplot_fig_to_rgb_array(fig, expand=True):
    fig.canvas.draw()
    buf = fig.canvas.tostring_rgb()
    ncols, nrows = fig.canvas.get_width_height()
    shape = (nrows, ncols, 3) if not expand else (1, nrows, ncols, 3)
    # return np.fromstring(buf, dtype=np.uint8).reshape(shape)
    return np.frombuffer(buf, dtype=np.uint8).reshape(shape)


def plot_grad_flow(named_parameters,
                   epoch: int,
                   tag_name: str,
                   summary_writer: SummaryWriter):
    """ Plots the gradients flowing through different layers in the net during training.
        Can be used for checking for possible gradient vanishing / exploding problsems.

        Usage: Plug this function in Trainer class after loss.backwards() as
        "plot_grad_flow(self.model.named_parameters())" to visualize the gradient flow

        From https://discuss.pytorch.org/t/check-gradient-flow-in-network/15063
    """
    ave_grads = []
    max_grads = []
    layers = []

    for n, p in named_parameters:
        if p.requires_grad and ("bias" not in n):
            layers.append(n)
            ave_grads.append(p.grad.abs().mean().cpu())
            max_grads.append(p.grad.abs().max().cpu())

    fig = plt.figure()
    plt.bar(np.arange(len(max_grads)), max_grads, alpha=0.1, lw=1, color="r")  # c
    plt.bar(np.arange(len(max_grads)), ave_grads, alpha=0.1, lw=1, color="b")
    plt.hlines(0, 0, len(ave_grads) + 1, lw=2, color="k")
    plt.xticks(range(0, len(ave_grads), 1), layers, rotation="vertical")
    plt.xlim(left=0, right=len(ave_grads))
    # plt.ylim(bottom=-0.001, top=0.02)  # zoom in on the lower gradient regions
    plt.ylim(bottom=-0.001, top=0.01)
    # plt.xlabel("Layers")
    plt.ylabel("average gradient")
    plt.title("Gradient flow")
    plt.grid(True)
    plt.legend([plt.Line2D([0], [0], color="r", lw=4),  # c
                plt.Line2D([0], [0], color="b", lw=4),
                plt.Line2D([0], [0], color="k", lw=4)], ['max-gradient', 'mean-gradient', 'zero-gradient'])
    plt.tight_layout()


    #np_array = pyplot_fig_to_rgb_array(fig)
    #torch_tensor = torch.from_numpy(np_array).squeeze(0).permute(2, 0, 1)

    summary_writer.add_figure(tag=f'train/grad_flow/{tag_name}', figure=fig, global_step=epoch)

    plt.close(fig)
