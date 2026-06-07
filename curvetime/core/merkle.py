import hashlib
from typing import List

class MerkleTree:
    def __init__(self, leaves: List[str]):
        self.leaves = leaves
        self.root = self._build(leaves)

    def _hash_pair(self, left: str, right: str) -> str:
        combined = left + right
        return hashlib.sha256(hashlib.sha256(combined.encode()).digest()).hexdigest()

    def _build(self, nodes: List[str]) -> str:
        if len(nodes) == 1:
            return nodes[0]
        new_level = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i+1] if i+1 < len(nodes) else left
            new_level.append(self._hash_pair(left, right))
        return self._build(new_level)