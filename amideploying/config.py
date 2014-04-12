import os
from yaml import load


def get_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.yml')
    with open(config_path, 'r') as fh:
        return load(fh)
