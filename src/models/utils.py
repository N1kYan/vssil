import torch
import torch.nn as nn


def get_img_coordinates(h: int, w: int, normalize: bool):
    """ TODO """
    x_range = torch.arange(w, dtype=torch.float32)
    y_range = torch.arange(h, dtype=torch.float32)
    if normalize:
        x_range = (x_range / (w - 1)) * 2 - 1
        y_range = (y_range / (h - 1)) * 2 - 1
    image_x = x_range.unsqueeze(0).repeat_interleave(h, 0)
    image_y = y_range.unsqueeze(0).repeat_interleave(w, 0).t()
    return image_x, image_y


def partial_load_state_dict(model: torch.nn.Module, loaded_dict: torch.ParameterDict):
    """ Loads all named parameters of the given model
        from the given loaded state_dict.

    :param model: The model whose parameters are to update
    :param loaded_dict: The state dict to update from
    """
    model_state_dict = model.state_dict()

    for name, param in loaded_dict.items():
        if name not in model_state_dict:
            continue
        if isinstance(param, torch.nn.Parameter):
            param = param.data
        model_state_dict[name].copy_(param)


def init_weights(m: torch.nn.Module, config: dict):
    if type(m) == nn.Conv2d:
        if config['model']['weight_init'] in ['he_uniform', 'kaiming_uniform']:
            torch.nn.init.kaiming_uniform_(m.weight)
            m.bias.data.fill_(0.01)
        if config['model']['weight_init'] == ['he_normal', 'kaiming_normal']:
            torch.nn.init.kaiming_normal_(m.weight)
            m.bias.data.fill_(0.01)
        if config['model']['weight_init'] == 'xavier_uniform':
            torch.nn.init.xavier_uniform_(m.weight)
            m.bias.data.fill_(0.01)
        if config['model']['weight_init'] == 'xavier_normal':
            torch.nn.init.xavier_normal_(m.weight)
            m.bias.data.fill_(0.01)
        if config['model']['weight_init'] == 'ones':
            torch.nn.init.ones_(m.weight)
            m.bias.data.fill_(1.00)


activation_dict = {
    'identity': nn.Identity,
    'id': nn.Identity,
    'sigmoid': nn.Sigmoid,
    'Sigmoid': nn.Sigmoid,
    'tanh': nn.Tanh,
    'relu': nn.ReLU,
    'ReLU': nn.ReLU,
    'RELU': nn.ReLU,
    'ELU': nn.ELU,
    'elu': nn.ELU,
    'LeakyRELU': nn.LeakyReLU,
    'LeakyReLU': nn.LeakyReLU,
    'LeakyRelu': nn.LeakyReLU,
    'PRELU': nn.PReLU,
    'PReLU': nn.PReLU,
    'prelu': nn.PReLU
}
