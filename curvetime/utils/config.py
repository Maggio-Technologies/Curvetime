import yaml
from typing import Dict

def load_config(path: str = "config/node.yaml") -> Dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f)

class ConsensusConfig:
    block_time = 10
    difficulty_adjustment_interval = 2016