# curvetime/consensus/dqn_agent.py
import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass


class DQNNetwork(nn.Module):
    """深度Q网络(DQN)"""
    
    def __init__(self, state_size: int, action_size: int, hidden_size: int = 256):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, action_size)
        )
        
    def forward(self, x):
        return self.network(x)


class DQNAgent:
    """
    DQN强化学习代理
    负责学习最优的挖矿策略和AI训练策略
    """
    
    def __init__(self, config: Dict):
        self.state_size = config.get('state_size', 128)
        self.action_size = config.get('action_size', 4)
        self.memory = deque(maxlen=config.get('memory_size', 10000))
        self.batch_size = config.get('batch_size', 64)
        self.gamma = config.get('gamma', 0.95)  # 折扣因子
        self.epsilon = config.get('epsilon', 1.0)  # 探索率
        self.epsilon_min = config.get('epsilon_min', 0.01)
        self.epsilon_decay = config.get('epsilon_decay', 0.995)
        self.learning_rate = config.get('learning_rate', 0.001)
        
        # 设备和模型
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.policy_net = DQNNetwork(self.state_size, self.action_size).to(self.device)
        self.target_net = DQNNetwork(self.state_size, self.action_size).to(self.device)
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=self.learning_rate)
        
        self.current_version = 0
        self._model_hash = None
        
        # 同步目标网络
        self.update_target_network()
        
    def get_action(self, state: np.ndarray) -> int:
        """选择行动"""
        if random.random() <= self.epsilon:
            return random.randrange(self.action_size)
        
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor)
            return q_values.argmax().item()
    
    def train_step(self, experiences: List) -> float:
        """训练一步"""
        if len(experiences) < self.batch_size:
            return 0.0
        
        # 构建训练批次
        states, actions, rewards, next_states, dones = zip(*experiences)
        
        states = torch.FloatTensor(np.array(states)).to(self.device)
        actions = torch.LongTensor(np.array(actions)).to(self.device)
        rewards = torch.FloatTensor(np.array(rewards)).to(self.device)
        next_states = torch.FloatTensor(np.array(next_states)).to(self.device)
        dones = torch.FloatTensor(np.array(dones)).to(self.device)
        
        # 计算当前Q值
        current_q_values = self.policy_net(states).gather(1, actions.unsqueeze(1))
        
        # 计算目标Q值
        with torch.no_grad():
            next_q_values = self.target_net(next_states).max(1)[0]
            target_q_values = rewards + (1 - dones) * self.gamma * next_q_values
        
        # 计算损失并更新
        loss = nn.MSELoss()(current_q_values.squeeze(), target_q_values)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        # 更新探索率
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        return loss.item()
    
    def update_target_network(self):
        """同步目标网络"""
        self.target_net.load_state_dict(self.policy_net.state_dict())
    
    def should_update_target(self) -> bool:
        """判断是否应该更新目标网络"""
        # 每次训练后都有一定概率更新
        return random.random() < 0.01
    
    def evaluate_block(self, block) -> float:
        """评估区块的AI贡献值"""
        # 计算区块中AI训练数据的贡献度
        ai_features = block.ai_state if block.ai_state else {}
        score = 0.0
        
        # AI训练数据贡献评分
        if 'model_update' in ai_features:
            score += 0.5
        if 'training_samples' in ai_features:
            score += min(len(ai_features['training_samples']) / 1000, 0.5)
        
        # 使用DQN进行评估
        state = np.zeros(self.state_size)
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor)
            score += q_values.mean().item() * 0.1
        
        return score
    
    def predict_nonce_range(self, prev_hash: str, tx_count: int) -> Optional[Tuple[int, int]]:
        """利用DQN预测Nonce搜索范围"""
        # 基于历史和当前区块链状态预测最优Nonce起始点
        # 此处简化实现
        return None
    
    def get_model_hash(self) -> str:
        """获取当前AI模型的哈希"""
        return self._model_hash or "0" * 64
    
    def aggregate_models(self, peer_updates: List):
        """联邦学习：聚合其他节点的模型更新"""
        if not peer_updates:
            return
        
        # 简单的平均聚合
        total_weights = {}
        for update in peer_updates:
            for name, param in update.items():
                if name not in total_weights:
                    total_weights[name] = []
                total_weights[name].append(param)
        
        # 计算平均并更新模型
        for name in total_weights:
            avg_weight = torch.mean(torch.stack(total_weights[name]), dim=0)
            self.policy_net.state_dict()[name].copy_(avg_weight)
        
        self.current_version += 1


class AIEnvironment:
    """AI训练环境封装(基于Gymnasium)"""
    
    def __init__(self):
        self.state_dim = 128
        self.action_dim = 4
        self._state_cache = None
        
    def get_state(self, blockchain, candidate) -> np.ndarray:
        """获取当前环境状态向量"""
        state = []
        
        # 区块链状态特征
        state.append(blockchain.get_difficulty())
        state.append(blockchain.get_height())
        state.append(len(blockchain.mempool.get_pending_transactions()))
        
        # AI状态特征
        state.append(candidate.ai_model_score)
        state.append(candidate.difficulty)
        
        # 填充到固定维度
        while len(state) < self.state_dim:
            state.append(0.0)
        
        return np.array(state[:self.state_dim], dtype=np.float32)
    
    def collect_experience(self, blockchain, max_samples: int = 1024) -> List:
        """收集训练经验"""
        # 实际实现中应从区块链历史中收集状态-行动-奖励数据
        return []