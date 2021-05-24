import yaml

from src.data.mime.mime_hd_kinect_dataset import MimeHDKinectRGB
from src.agents.tcn_agent import TCN_Agent

tcn_conf = yaml.safe_load(open('src/configs/tcn.yml'))

data_set = MimeHDKinectRGB(
    base_path='/home/yannik/vssil/datasets',
    tasks=tcn_conf['data']['tasks'],
    timesteps_per_sample=tcn_conf['model']['n_frames'],  # 10
    overlap=tcn_conf['data']['overlap'],
    img_scale_factor=tcn_conf['data']['img_scale_factor']
)

tcn_agent = TCN_Agent(
    dataset=data_set,
    config=tcn_conf
)

tcn_agent.train(config=tcn_conf)