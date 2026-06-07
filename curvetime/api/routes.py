# curvetime/api/routes.py
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict
import uvicorn

from ..node import CurveTimeNode
from ..core.transaction import Transaction
from ..core.block import Block


# 数据模型定义
class TransactionCreate(BaseModel):
    sender: str
    receiver: str
    amount: float
    data: Optional[str] = None
    signature: str


class BlockResponse(BaseModel):
    hash: str
    height: int
    timestamp: int
    transactions: List[Dict]
    size: int
    ai_state: Optional[Dict] = None


def create_api_app(node: CurveTimeNode) -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(title="CurveTime Blockchain API", 
                  description="可商用的区块链系统API", 
                  version="1.0.0")
    
    security = HTTPBearer()
    
    # ---------- 区块链核心API ----------
    @app.get("/api/blockchain/info", response_model=Dict)
    async def get_blockchain_info():
        """获取区块链基本信息"""
        return {
            "chain_name": node.blockchain.name,
            "height": node.blockchain.get_height(),
            "difficulty": node.consensus.difficulty,
            "total_transactions": node.blockchain.total_transactions,
            "last_block_time": node.blockchain.get_last_block().header.timestamp,
            "ai_model_version": node.dqn_agent.current_version
        }
    
    @app.get("/api/block/{block_hash}", response_model=BlockResponse)
    async def get_block_by_hash(block_hash: str):
        """根据哈希获取区块"""
        block = node.blockchain.get_block_by_hash(block_hash)
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")
        return block.to_dict()
    
    @app.get("/api/block/height/{height}", response_model=BlockResponse)
    async def get_block_by_height(height: int):
        """根据高度获取区块"""
        block = node.blockchain.get_block_by_height(height)
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")
        return block.to_dict()
    
    @app.get("/api/transaction/{tx_hash}", response_model=Dict)
    async def get_transaction(tx_hash: str):
        """根据哈希获取交易"""
        tx = node.blockchain.get_transaction(tx_hash)
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return tx.to_dict()
    
    @app.post("/api/transaction", response_model=Dict)
    async def submit_transaction(tx: TransactionCreate, background_tasks: BackgroundTasks):
        """提交交易"""
        # 创建交易对象
        transaction = Transaction(
            sender=tx.sender,
            receiver=tx.receiver,
            amount=tx.amount,
            data=tx.data or "",
            signature=tx.signature
        )
        
        # 验证交易
        if not node.validate_transaction(transaction):
            raise HTTPException(status_code=400, detail="Invalid transaction")
        
        # 添加到内存池
        node.mempool.add_transaction(transaction)
        
        # 广播到网络
        background_tasks.add_task(node.broadcast_transaction, transaction)
        
        return {"status": "success", "tx_hash": transaction.hash}
    
    @app.post("/api/block/mine", response_model=Dict)
    async def start_mining():
        """触发挖矿"""
        if node.consensus.running:
            raise HTTPException(status_code=409, detail="Mining already in progress")
        
        asyncio.create_task(node.consensus.start_mining(node.address))
        return {"status": "mining_started"}
    
    @app.get("/api/mempool", response_model=List[Dict])
    async def get_mempool():
        """获取交易内存池"""
        return [tx.to_dict() for tx in node.mempool.get_all_transactions()]
    
    # ---------- 节点管理API ----------
    @app.post("/api/node/register")
    async def register_node(peer_address: str, background_tasks: BackgroundTasks):
        """注册新的对等节点"""
        success = await node.network.connect_peer(peer_address)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to connect to peer")
        
        background_tasks.add_task(node.sync_chain_with_peer, peer_address)
        return {"status": "registered", "peer": peer_address}
    
    @app.get("/api/node/peers", response_model=List[str])
    async def get_peers():
        """获取已连接的节点列表"""
        return list(node.network.peers)
    
    # ---------- AI相关API ----------
    @app.post("/api/ai/train")
    async def trigger_ai_training(background_tasks: BackgroundTasks):
        """触发AI模型训练"""
        background_tasks.add_task(node.dqn_agent.train_step, node.get_training_data())
        return {"status": "training_started"}
    
    @app.get("/api/ai/model/info", response_model=Dict)
    async def get_ai_model_info():
        """获取AI模型信息"""
        return {
            "version": node.dqn_agent.current_version,
            "epsilon": node.dqn_agent.epsilon,
            "memory_size": len(node.dqn_agent.memory)
        }
    
    @app.post("/api/ai/model/update")
    async def update_ai_model(model_data: Dict):
        """更新AI模型参数(用于节点间同步)"""
        success = node.dqn_agent.aggregate_models([model_data])
        return {"status": "updated" if success else "failed"}
    
    # ---------- 管理API ----------
    @app.get("/api/health", response_model=Dict)
    async def health_check():
        """健康检查"""
        return {
            "status": "healthy",
            "blockchain_height": node.blockchain.get_height(),
            "peer_count": len(node.network.peers),
            "mempool_size": len(node.mempool.get_pending_transactions())
        }
    
    return app


def run_api_server(node: CurveTimeNode, host: str = "0.0.0.0", port: int = 8000):
    """启动API服务器"""
    app = create_api_app(node)
    uvicorn.run(app, host=host, port=port, log_level="info")