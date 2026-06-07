import hashlib
import json
import time
from typing import Dict, Optional
from dataclasses import dataclass
from ..crypto.keys import verify_signature, sign_message

@dataclass
class Transaction:
    sender: str
    receiver: str
    amount: float
    fee: float = 0.0
    data: str = ""
    timestamp: int = 0
    signature: str = ""
    hash: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = int(time.time())
        if not self.hash:
            self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        content = f"{self.sender}{self.receiver}{self.amount}{self.fee}{self.data}{self.timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()

    def sign(self, private_key_hex: str):
        self.signature = sign_message(self.compute_hash(), private_key_hex)

    def verify_signature(self) -> bool:
        if not self.signature:
            return False
        return verify_signature(self.compute_hash(), self.signature, self.sender)

    @classmethod
    def create_coinbase(cls, height: int, address: str) -> "Transaction":
        tx = cls(
            sender="COINBASE",
            receiver=address,
            amount=12.5,
            fee=0,
            data=f"Coinbase for block {height}",
            timestamp=int(time.time())
        )
        tx.hash = tx.compute_hash()
        return tx

    def serialize(self) -> bytes:
        return json.dumps({
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "fee": self.fee,
            "data": self.data,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "hash": self.hash
        }).encode()

    @classmethod
    def from_dict(cls, data: Dict) -> "Transaction":
        return cls(**data)

    def to_dict(self) -> Dict:
        return {
            "hash": self.hash,
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "fee": self.fee,
            "timestamp": self.timestamp
        }

class UTXOManager:
    def __init__(self, blockchain):
        self.blockchain = blockchain