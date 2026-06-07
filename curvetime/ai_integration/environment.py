import numpy as np

class AIEnvironment:
    def __init__(self):
        self.state_dim = 128

    def get_state(self, blockchain, candidate) -> np.ndarray:
        # 返回状态向量
        state = [0.0] * self.state_dim
        state[0] = blockchain.get_difficulty()
        state[1] = blockchain.get_height()
        return np.array(state, dtype=np.float32)

    def collect_experience(self, blockchain, max_samples=1024):
        return []