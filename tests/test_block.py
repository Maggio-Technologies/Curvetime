import unittest
from curvetime.core.block import Block, BlockHeader
from curvetime.core.transaction import Transaction

class TestBlock(unittest.TestCase):
    def test_genesis(self):
        block = Block.create_genesis_block()
        self.assertEqual(block.header.height, 0)
        self.assertTrue(block.validate_pow(block.header.bits))