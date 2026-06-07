# curvetime/core/block.py
import hashlib
import json
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from ..crypto.hash import double_sha256
from .transaction import Transaction, TransactionValidator
from .merkle import MerkleTree


@dataclass
class BlockHeader:
    """区块头结构"""
    version: int = 1
    prev_block_hash: str = ""
    merkle_root: str = ""
    timestamp: int = 0
    nonce: int = 0
    bits: int = 0
    height: int = 0
    block_hash: str = ""


class Block:
    """区块数据结构"""
    
    def __init__(self, 
                 header: BlockHeader,
                 transactions: List[Transaction],
                 ai_state: Optional[Dict] = None):  # AI状态数据(CurveTime特有)
        self.header = header
        self.transactions = transactions
        self.ai_state = ai_state or {}
        self._hash = None
    
    @classmethod
    def create_genesis_block(cls) -> "Block":
        """创世区块"""
        header = BlockHeader(
            version=1,
            prev_block_hash="0" * 64,
            merkle_root="",
            timestamp=int(time.time()),
            nonce=0,
            bits=0x1d00ffff,  # 初始难度值
            height=0
        )
        genesis_tx = Transaction.create_coinbase(0, "CurveTimeGenesis")
        block = cls(header, [genesis_tx])
        block.header.merkle_root = block.calculate_merkle_root()
        block.header.block_hash = block.compute_hash()
        return block
    
    def calculate_merkle_root(self) -> str:
        """计算Merkle根"""
        if not self.transactions:
            return "0" * 64
        tx_hashes = [tx.hash for tx in self.transactions]
        tree = MerkleTree(tx_hashes)
        return tree.root
    
    def compute_hash(self) -> str:
        """计算区块哈希"""
        header_dict = asdict(self.header)
        # 排除block_hash字段自身
        header_dict.pop('block_hash', None)
        block_string = json.dumps(header_dict, sort_keys=True)
        return double_sha256(block_string.encode())
    
    def validate(self, prev_block_hash: str, prev_height: int, 
                 target_bits: int) -> bool:
        """验证区块有效性"""
        # 验证前块哈希
        if self.header.prev_block_hash != prev_block_hash:
            return False
        
        # 验证高度连续性
        if self.header.height != prev_height + 1:
            return False
        
        # 验证工作量证明
        if not self.validate_pow(target_bits):
            return False
        
        # 验证Merkle根
        if self.header.merkle_root != self.calculate_merkle_root():
            return False
        
        # 验证每一笔交易
        for tx in self.transactions:
            if not TransactionValidator.validate(tx):
                return False
        
        return True
    
    def validate_pow(self, target_bits: int) -> bool:
        """验证工作量证明"""
        hash_int = int(self.header.block_hash, 16)
        target = (1 << (256 - target_bits)) if target_bits < 256 else 1
        return hash_int < target
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "header": asdict(self.header),
            "transactions": [tx.to_dict() for tx in self.transactions],
            "ai_state": self.ai_state,
            "size": len(str(self))
        }