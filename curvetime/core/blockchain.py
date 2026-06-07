from typing import Optional, List
from .block import Block
from ..storage.chain_db import BlockchainDB
from ..storage.mempool import Mempool

class Blockchain:
    def __init__(self, db: BlockchainDB, mempool: Mempool):
        self.db = db
        self.mempool = mempool
        self.name = "CurveTime"
        self.total_transactions = 0
        if db.get_height() == -1:
            self._init_genesis()

    def _init_genesis(self):
        genesis = Block.create_genesis_block()
        self.db.put_block(genesis)
        self.total_transactions = len(genesis.transactions)

    def get_last_block(self) -> Optional[Block]:
        return self.db.get_last_block()

    def get_height(self) -> int:
        return self.db.get_height()

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        return self.db.get_block_by_hash(block_hash)

    def get_block_by_height(self, height: int) -> Optional[Block]:
        return self.db.get_block_by_height(height)

    def add_block(self, block: Block) -> bool:
        last = self.get_last_block()
        if not block.validate(last.header.block_hash, last.header.height, block.header.bits):
            return False
        self.db.put_block(block)
        self.total_transactions += len(block.transactions)
        return True

    def get_balance(self, address: str) -> float:
        # 简化：遍历UTXO，实际应使用UTXO管理器
        return 100.0  # 占位

    def is_double_spend(self, tx) -> bool:
        return False  # 占位

    def get_transaction(self, tx_hash: str):
        return self.db.get_transaction(tx_hash)

    def get_timespan(self) -> float:
        # 返回最近2016个区块的时间跨度
        return 2016 * 10  # 占位

    def get_difficulty(self) -> int:
        last = self.get_last_block()
        return last.header.bits if last else 1