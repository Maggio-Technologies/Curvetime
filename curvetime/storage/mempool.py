from typing import List, Optional
from ..core.transaction import Transaction

class Mempool:
    def __init__(self, max_size: int = 10000):
        self.txs = {}
        self.max_size = max_size

    def add_transaction(self, tx: Transaction):
        if len(self.txs) >= self.max_size:
            # 简单驱逐策略
            self.txs.pop(next(iter(self.txs)))
        self.txs[tx.hash] = tx

    def get_pending_transactions(self, limit: int = 2000) -> List[Transaction]:
        return list(self.txs.values())[:limit]

    def remove_transactions(self, txs: List[Transaction]):
        for tx in txs:
            self.txs.pop(tx.hash, None)

    def get_all_transactions(self) -> List[Transaction]:
        return list(self.txs.values())