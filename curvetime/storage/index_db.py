import plyvel
import struct

class IndexDB:
    def __init__(self, path: str):
        self.db = plyvel.DB(path, create_if_missing=True)

    def put_tx_index(self, tx_hash: str, block_hash: str, height: int):
        key = b'TX:' + tx_hash.encode()
        value = struct.pack('>Q', height) + block_hash.encode()
        self.db.put(key, value)

    def get_tx_location(self, tx_hash: str):
        data = self.db.get(b'TX:' + tx_hash.encode())
        if data:
            height = struct.unpack('>Q', data[:8])[0]
            block_hash = data[8:].decode()
            return height, block_hash
        return None, None

    def close(self):
        self.db.close()