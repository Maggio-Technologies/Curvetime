# curvetime/storage/chain_db.py
import os
import struct
import plyvel
from typing import Optional, List, Dict, Any
from ..core.block import Block
from ..core.transaction import Transaction


class BlockchainDB:
    """区块链数据库(基于LevelDB)"""
    
    def __init__(self, db_path: str = "data/blockchain_db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self.db = plyvel.DB(db_path, create_if_missing=True)
        
        # 键前缀
        self.PREFIX_BLOCK = b'B'      # B{hash} -> 区块数据
        self.PREFIX_HEIGHT = b'H'     # H{height:8byte} -> 区块哈希
        self.PREFIX_TX = b'T'         # T{tx_hash} -> 交易数据
        self.PREFIX_UTXO = b'U'       # U{outpoint} -> UTXO
        
    def put_block(self, block: Block):
        """存储区块"""
        block_key = self.PREFIX_BLOCK + block.header.block_hash.encode()
        block_data = block.serialize()
        self.db.put(block_key, block_data)
        
        # 存储高度->哈希索引
        height_key = self.PREFIX_HEIGHT + struct.pack('>Q', block.header.height)
        self.db.put(height_key, block.header.block_hash.encode())
        
        # 存储该区块中的所有交易
        for tx in block.transactions:
            tx_key = self.PREFIX_TX + tx.hash.encode()
            self.db.put(tx_key, tx.serialize())
    
    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        """根据哈希获取区块"""
        key = self.PREFIX_BLOCK + block_hash.encode()
        data = self.db.get(key)
        if data:
            return Block.deserialize(data)
        return None
    
    def get_block_by_height(self, height: int) -> Optional[Block]:
        """根据高度获取区块"""
        height_key = self.PREFIX_HEIGHT + struct.pack('>Q', height)
        block_hash = self.db.get(height_key)
        if block_hash:
            return self.get_block_by_hash(block_hash.decode())
        return None
    
    def get_last_block(self) -> Optional[Block]:
        """获取最新区块"""
        # 迭代获取最大高度的区块
        for key, value in self.db.iterator(prefix=self.PREFIX_HEIGHT, reverse=True):
            block_hash = value.decode()
            return self.get_block_by_hash(block_hash)
        return None
    
    def get_height(self) -> int:
        """获取当前区块链高度"""
        for key, _ in self.db.iterator(prefix=self.PREFIX_HEIGHT, reverse=True):
            return struct.unpack('>Q', key[1:])[0]
        return -1
    
    def put_utxo(self, outpoint: str, utxo_data: bytes):
        """存储UTXO"""
        key = self.PREFIX_UTXO + outpoint.encode()
        self.db.put(key, utxo_data)
    
    def get_utxo(self, outpoint: str) -> Optional[bytes]:
        """获取UTXO"""
        key = self.PREFIX_UTXO + outpoint.encode()
        return self.db.get(key)
    
    def delete_utxo(self, outpoint: str):
        """删除UTXO"""
        key = self.PREFIX_UTXO + outpoint.encode()
        self.db.delete(key)
    
    def close(self):
        """关闭数据库"""
        self.db.close()