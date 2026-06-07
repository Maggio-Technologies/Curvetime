"""消息协议定义：消息类型、序列化、校验"""
import json
import time
import hashlib
from enum import IntEnum
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict


class MessageType(IntEnum):
    """消息类型枚举，与p2p_node中保持一致并扩展"""
    NEW_BLOCK = 1
    NEW_TRANSACTION = 2
    GET_BLOCKS = 3
    GET_BLOCK = 4
    INV = 5               # 清单（区块/交易哈希列表）
    GET_DATA = 6          # 根据哈希获取完整数据
    AI_MODEL_UPDATE = 7
    AI_MODEL_REQUEST = 8
    PEER_ANNOUNCE = 9     # 节点广播自身地址
    PEER_LIST = 10        # 节点列表回复
    PING = 11
    PONG = 12
    GOSSIP_TX = 13        # 专门用于Gossip传播的交易
    GOSSIP_BLOCK = 14
    SYNC_REQUEST = 15
    SYNC_RESPONSE = 16


@dataclass
class Message:
    """统一消息结构"""
    type: MessageType
    payload: Any          # 字典或可序列化对象
    sender_id: str        # 节点ID（通常为IP:Port）
    timestamp: float
    nonce: int = 0
    signature: str = ""   # 可选签名，用于防伪造

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()
        if self.nonce == 0:
            self.nonce = int(time.time() * 1000) % (2**32)

    def serialize(self) -> bytes:
        """序列化为JSON字节流"""
        data = {
            "type": self.type.value,
            "payload": self.payload,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "signature": self.signature
        }
        return json.dumps(data, ensure_ascii=False).encode('utf-8')

    @classmethod
    def deserialize(cls, data: bytes) -> 'Message':
        obj = json.loads(data.decode('utf-8'))
        return cls(
            type=MessageType(obj["type"]),
            payload=obj["payload"],
            sender_id=obj["sender_id"],
            timestamp=obj["timestamp"],
            nonce=obj["nonce"],
            signature=obj.get("signature", "")
        )

    def compute_hash(self) -> str:
        """计算消息内容的哈希，用于去重和签名验证"""
        content = f"{self.type.value}{self.sender_id}{self.timestamp}{self.nonce}{json.dumps(self.payload, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

    def sign(self, private_key_b64: str):
        """使用节点私钥签名消息"""
        from ...crypto.keys import sign_message
        self.signature = sign_message(self.compute_hash(), private_key_b64)

    def verify_signature(self, public_key_b64: str) -> bool:
        """验证签名"""
        from ...crypto.keys import verify_signature
        return verify_signature(self.compute_hash(), self.signature, public_key_b64)


class Protocol:
    """协议辅助类，提供消息构造的工厂方法"""

    @staticmethod
    def new_block_msg(sender_id: str, block_data: dict) -> Message:
        return Message(
            type=MessageType.NEW_BLOCK,
            payload={"block_data": block_data},
            sender_id=sender_id
        )

    @staticmethod
    def new_transaction_msg(sender_id: str, tx_data: dict) -> Message:
        return Message(
            type=MessageType.NEW_TRANSACTION,
            payload={"tx_data": tx_data},
            sender_id=sender_id
        )

    @staticmethod
    def get_blocks_msg(sender_id: str, from_height: int, to_height: int = -1) -> Message:
        return Message(
            type=MessageType.GET_BLOCKS,
            payload={"from": from_height, "to": to_height},
            sender_id=sender_id
        )

    @staticmethod
    def inv_msg(sender_id: str, items: list) -> Message:
        """items: [{"type": "block", "hash": "..."}, {"type": "tx", "hash": "..."}]"""
        return Message(
            type=MessageType.INV,
            payload={"items": items},
            sender_id=sender_id
        )

    @staticmethod
    def get_data_msg(sender_id: str, items: list) -> Message:
        return Message(
            type=MessageType.GET_DATA,
            payload={"items": items},
            sender_id=sender_id
        )

    @staticmethod
    def peer_announce_msg(sender_id: str, listen_port: int, services: int = 0) -> Message:
        return Message(
            type=MessageType.PEER_ANNOUNCE,
            payload={"port": listen_port, "services": services},
            sender_id=sender_id
        )

    @staticmethod
    def peer_list_msg(sender_id: str, peers: list) -> Message:
        """peers: ["ip:port", ...]"""
        return Message(
            type=MessageType.PEER_LIST,
            payload={"peers": peers},
            sender_id=sender_id
        )

    @staticmethod
    def ping_msg(sender_id: str) -> Message:
        return Message(type=MessageType.PING, payload={}, sender_id=sender_id)

    @staticmethod
    def pong_msg(sender_id: str, original_timestamp: float) -> Message:
        return Message(
            type=MessageType.PONG,
            payload={"echo": original_timestamp},
            sender_id=sender_id
        )