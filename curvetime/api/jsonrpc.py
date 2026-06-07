# curvetime/api/jsonrpc.py
import json
import asyncio
from typing import Dict, Any, Optional
from jsonrpcserver import method, async_dispatch
from jsonrpcserver.exceptions import InvalidParams

from ..node import CurveTimeNode


class JSONRPCServer:
    """JSON-RPC服务器实现"""
    
    def __init__(self, node: CurveTimeNode):
        self.node = node
        self._register_methods()
    
    def _register_methods(self):
        """注册RPC方法"""
        
        @method(name="bc_getBlockByHash")
        async def get_block_by_hash(params: Dict) -> Optional[Dict]:
            block_hash = params.get('hash')
            if not block_hash:
                raise InvalidParams("Missing 'hash' parameter")
            block = self.node.blockchain.get_block_by_hash(block_hash)
            return block.to_dict() if block else None
        
        @method(name="bc_getBlockByNumber")
        async def get_block_by_number(params: Dict) -> Optional[Dict]:
            height = params.get('number')
            if height is None:
                raise InvalidParams("Missing 'number' parameter")
            block = self.node.blockchain.get_block_by_height(height)
            return block.to_dict() if block else None
        
        @method(name="bc_sendTransaction")
        async def send_transaction(params: Dict) -> str:
            required = ['from', 'to', 'value', 'signature']
            for field in required:
                if field not in params:
                    raise InvalidParams(f"Missing '{field}' parameter")
            
            tx = Transaction(
                sender=params['from'],
                receiver=params['to'],
                amount=params['value'],
                data=params.get('data', ''),
                signature=params['signature']
            )
            
            if not self.node.validate_transaction(tx):
                raise InvalidParams("Invalid transaction")
            
            self.node.mempool.add_transaction(tx)
            await self.node.broadcast_transaction(tx)
            return tx.hash
        
        @method(name="bc_getTransactionByHash")
        async def get_transaction_by_hash(params: Dict) -> Optional[Dict]:
            tx_hash = params.get('hash')
            if not tx_hash:
                raise InvalidParams("Missing 'hash' parameter")
            tx = self.node.blockchain.get_transaction(tx_hash)
            return tx.to_dict() if tx else None
        
        @method(name="bc_getBlockCount")
        async def get_block_count() -> int:
            return self.node.blockchain.get_height() + 1
        
        @method(name="bc_getDifficulty")
        async def get_difficulty() -> int:
            return self.node.consensus.difficulty
        
        @method(name="bc_getPeerCount")
        async def get_peer_count() -> int:
            return len(self.node.network.peers)
        
        @method(name="bc_getAINetworkInfo")
        async def get_ai_network_info() -> Dict:
            return {
                "ai_model_version": self.node.dqn_agent.current_version,
                "epsilon": self.node.dqn_agent.epsilon,
                "training_iterations": self.node.dqn_agent.training_iterations
            }
        
        @method(name="bc_mineBlock")
        async def mine_block(force: bool = False) -> bool:
            if not self.node.consensus.running or force:
                asyncio.create_task(self.node.consensus.start_mining(self.node.address))
                return True
            return False
    
    async def handle_request(self, request_json: str) -> str:
        """处理JSON-RPC请求"""
        response = await async_dispatch(request_json)
        return json.dumps(response, default=str)