#!/usr/bin/env python3
"""CurveTime 区块链节点主入口"""

import asyncio
import signal
import sys
from typing import Optional

from .core.blockchain import Blockchain
from .core.block import Block
from .core.transaction import Transaction
from .consensus.curvetime_base import CurveTimeConsensus
from .network.p2p_node import P2PNode
from .network.protocol import MessageType
from .storage.chain_db import BlockchainDB
from .storage.mempool import Mempool
from .storage.index_db import IndexDB
from .api.routes import run_api_server
from .api.jsonrpc import JSONRPCServer
from .utils.config import load_config
from .utils.logger import setup_logger


class CurveTimeNode:
    """
    CurveTime 区块链节点
    整合区块链核心、共识引擎、P2P网络、API 服务和 AI 训练组件
    """

    def __init__(self, config_path: str = "config/node.yaml"):
        # 加载配置
        self.config = load_config(config_path)
        self.logger = setup_logger(
            self.config['node']['name'],
            level=self.config['logging'].get('level', 'INFO')
        )

        # 存储层
        self.db = BlockchainDB(self.config['storage']['chain_db_path'])
        self.index_db = IndexDB(self.config['storage'].get('index_db_path', './data/index_db'))
        self.mempool = Mempool(self.config['storage']['mempool_size'])

        # 区块链核心
        self.blockchain = Blockchain(self.db, self.mempool)

        # 共识引擎（包含 DQN 代理）
        self.consensus = CurveTimeConsensus(
            self.blockchain,
            self.config['consensus']['dqn'],
            self.config['consensus']['reward']
        )
        # 将共识的 DQN 代理暴露给外部
        self.dqn_agent = self.consensus.dqn_agent

        # P2P 网络层
        self.network = P2PNode(
            host=self.config['network']['host'],
            port=self.config['network']['port'],
            bootstrap_peers=self.config['network']['bootstrap_peers'],
            max_peers=self.config['network'].get('max_connections', 100),
            gossip_fanout=self.config['network'].get('gossip_fanout', 3),
            ping_interval=self.config['network'].get('ping_interval', 60.0)
        )

        # JSON-RPC 服务器
        self.jsonrpc = JSONRPCServer(self)

        # 节点地址（用于 coinbase）
        self.address = self.config['node'].get('address', f"http://localhost:{self.config['api']['port']}")

        # 运行标志
        self._running = False
        self._api_task = None
        self._rpc_task = None

        # 注册网络消息处理器
        self._setup_network_handlers()

        self.logger.info(f"Node initialized: {self.config['node']['name']}")

    def _setup_network_handlers(self):
        """注册 P2P 消息处理器，将网络消息转化为本地事件"""
        async def on_new_block(payload: dict, sender_ip: str):
            """收到新区块"""
            block_data = payload.get('block_data')
            if not block_data:
                return
            block = Block.deserialize(block_data)
            # 验证并添加区块
            if await self.blockchain.add_block(block):
                self.logger.info(f"Received new block #{block.header.height} from {sender_ip}")
                # 从内存池中移除已打包交易
                self.mempool.remove_transactions(block.transactions)
                # 触发共识的难度调整（如果必要）
                self.consensus.update_difficulty()
            else:
                self.logger.warning(f"Invalid block received from {sender_ip}")

        async def on_new_transaction(payload: dict, sender_ip: str):
            """收到新交易"""
            tx_data = payload.get('tx_data')
            if not tx_data:
                return
            tx = Transaction.from_dict(tx_data)
            if self.validate_transaction(tx):
                self.mempool.add_transaction(tx)
                self.logger.debug(f"Received transaction {tx.hash} from {sender_ip}")
            else:
                self.logger.debug(f"Invalid transaction from {sender_ip}")

        async def on_ai_model_update(payload: dict, sender_ip: str):
            """收到 AI 模型更新（联邦学习）"""
            model_weights = payload.get('model_weights')
            if model_weights:
                self.dqn_agent.aggregate_models([model_weights])
                self.logger.debug(f"AI model updated from {sender_ip}")

        # 注册处理器到 Gossip (Gossip 内部通过回调调用这些函数)
        # 注意：Gossip 的 register_callback 需要接收 (msg, sender_ip)
        # 我们包装一下
        async def wrap_new_block(msg, sender_ip):
            await on_new_block(msg.payload, sender_ip)
        async def wrap_new_tx(msg, sender_ip):
            await on_new_transaction(msg.payload, sender_ip)
        async def wrap_ai_update(msg, sender_ip):
            await on_ai_model_update(msg.payload, sender_ip)

        self.network.gossip.register_callback(MessageType.NEW_BLOCK, wrap_new_block)
        self.network.gossip.register_callback(MessageType.NEW_TRANSACTION, wrap_new_tx)
        self.network.gossip.register_callback(MessageType.AI_MODEL_UPDATE, wrap_ai_update)

        # 也可为节点发现注册处理器（如果需要自定义，但 PeerDiscovery 已自带）
        self.logger.info("Network handlers registered")

    def validate_transaction(self, tx: Transaction) -> bool:
        """验证交易有效性"""
        # 签名验证
        if not tx.verify_signature():
            return False
        # 余额检查（简化，实际需要 UTXO 管理）
        balance = self.blockchain.get_balance(tx.sender)
        if balance < tx.amount + tx.fee:
            return False
        # 防止双花（简单检查是否已在内存池或链上）
        if self.blockchain.is_double_spend(tx):
            return False
        return True

    async def broadcast_transaction(self, tx: Transaction):
        """广播交易到网络（通过 Gossip）"""
        tx_data = tx.to_dict()
        await self.network.broadcast_message(MessageType.NEW_TRANSACTION, {"tx_data": tx_data}, ttl=3)

    async def broadcast_block(self, block: Block):
        """广播新区块到网络"""
        block_data = block.serialize()
        await self.network.broadcast_message(MessageType.NEW_BLOCK, {"block_data": block_data}, ttl=2)

    async def start(self):
        """启动节点所有服务"""
        if self._running:
            self.logger.warning("Node already running")
            return

        self._running = True
        self.logger.info("Starting CurveTime node...")

        # 启动 P2P 网络（内部会启动 Gossip 和 PeerDiscovery）
        await self.network.start()

        # 启动共识挖矿（如果配置开启）
        if self.config['consensus']['auto_mine']:
            asyncio.create_task(self.consensus.start_mining(self.address))
            self.logger.info("Auto-mining enabled")

        # 启动 REST API 服务
        self._api_task = asyncio.create_task(
            run_api_server(self, self.config['api']['host'], self.config['api']['port'])
        )
        self.logger.info(f"REST API listening on {self.config['api']['host']}:{self.config['api']['port']}")

        # 启动 JSON-RPC 服务（如果需要独立端口，否则可通过 API 路由）
        if self.config.get('rpc', {}).get('enabled', False):
            self._rpc_task = asyncio.create_task(
                self._run_jsonrpc_server()
            )
            self.logger.info(f"JSON-RPC listening on {self.config['rpc']['host']}:{self.config['rpc']['port']}")

        self.logger.info(f"Node {self.config['node']['name']} started successfully")

    async def _run_jsonrpc_server(self):
        """运行 JSON-RPC HTTP 服务器（基于 aiohttp）"""
        from aiohttp import web

        async def handle_rpc(request):
            request_json = await request.text()
            response = await self.jsonrpc.handle_request(request_json)
            return web.Response(text=response, content_type='application/json')

        app = web.Application()
        app.router.add_post('/', handle_rpc)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner,
                          host=self.config['rpc']['host'],
                          port=self.config['rpc']['port'])
        await site.start()
        # 保持运行直到节点停止
        while self._running:
            await asyncio.sleep(1)

    async def stop(self):
        """优雅停止节点"""
        if not self._running:
            return
        self.logger.info("Stopping node...")
        self._running = False

        # 停止共识引擎
        self.consensus.running = False

        # 停止网络层
        await self.network.stop()

        # 取消 API 和 RPC 任务
        if self._api_task:
            self._api_task.cancel()
            try:
                await self._api_task
            except asyncio.CancelledError:
                pass
        if self._rpc_task:
            self._rpc_task.cancel()
            try:
                await self._rpc_task
            except asyncio.CancelledError:
                pass

        # 关闭数据库
        self.db.close()
        self.index_db.close()

        self.logger.info("Node stopped")

    def get_training_data(self):
        """为 DQN 代理收集训练数据（占位实现）"""
        # 实际应从区块链历史中提取状态-动作-奖励数据
        return []


# 主入口
async def main():
    import argparse
    parser = argparse.ArgumentParser(description='CurveTime Blockchain Node')
    parser.add_argument('-c', '--config', default='config/node.yaml', help='Configuration file path')
    args = parser.parse_args()

    node = CurveTimeNode(args.config)

    # 设置信号处理
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(node.stop()))

    try:
        await node.start()
        # 保持运行直到被停止
        while node._running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await node.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutdown requested")