import asyncio
from typing import List, Optional
from .dqn_agent import DQNAgent, AIEnvironment
from .reward_model import RewardModel
from ..core.block import Block, BlockHeader
from ..core.transaction import Transaction
from ..storage.mempool import Mempool
from ..utils.config import ConsensusConfig

class CurveTimeConsensus:
    def __init__(self, blockchain, dqn_config: dict, reward_config: dict):
        self.blockchain = blockchain
        self.dqn_agent = DQNAgent(dqn_config)
        self.ai_env = AIEnvironment()
        self.reward_model = RewardModel(reward_config)
        self.config = ConsensusConfig()
        self.running = False
        self.difficulty = 1
        self.mempool = blockchain.mempool

    async def start_mining(self, node_address: str):
        self.running = True
        while self.running:
            txs = self.mempool.get_pending_transactions(limit=2000)
            if not txs:
                await asyncio.sleep(0.1)
                continue
            candidate = await self._prepare_candidate(txs, node_address)
            solution = await self._pow_search(candidate)
            if solution:
                await self._submit_block(candidate.block, solution)
            await asyncio.sleep(0)

    async def _prepare_candidate(self, txs: List[Transaction], addr: str):
        prev = self.blockchain.get_last_block()
        height = prev.header.height + 1
        coinbase = Transaction.create_coinbase(height, addr)
        header = BlockHeader(
            prev_block_hash=prev.header.block_hash,
            height=height,
            bits=self.difficulty,
            timestamp=int(asyncio.get_event_loop().time())
        )
        block = Block(header, [coinbase] + txs)
        block.header.merkle_root = block.calculate_merkle_root()
        return block

    async def _pow_search(self, block: Block) -> Optional[int]:
        target = (1 << (256 - block.header.bits)) if block.header.bits < 256 else 1
        for nonce in range(2**32):
            block.header.nonce = nonce
            block.header.block_hash = block.compute_hash()
            if int(block.header.block_hash, 16) < target:
                return nonce
            if nonce % 10000 == 0:
                await asyncio.sleep(0)
        return None

    async def _submit_block(self, block: Block, nonce: int):
        block.header.nonce = nonce
        block.header.block_hash = block.compute_hash()
        if self.validate_block(block):
            await self.blockchain.add_block(block)
            # 广播在node层处理
            self.reward_model.grant_ai_reward(block)
            self.update_difficulty()

    def validate_block(self, block: Block) -> bool:
        prev = self.blockchain.get_last_block()
        return block.validate(prev.header.block_hash, prev.header.height, self.difficulty)

    def update_difficulty(self):
        # 简单调整
        pass