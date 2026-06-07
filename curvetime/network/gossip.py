"""Gossip协议实现：可靠、低冗余的消息广播"""
import asyncio
import random
import time
from typing import Set, Dict, List, Optional, Callable, Any
from collections import deque
import hashlib

from .protocol import Message, MessageType, Protocol
from ...utils.logger import setup_logger


class Gossip:
    """
    Gossip协议组件
    功能：
    - 消息去重（基于哈希）
    - 随机选择扇出节点（fanout）
    - 定期推送未确认消息
    - 消息生命周期管理
    """

    def __init__(self,
                 node_id: str,
                 network,
                 fanout: int = 3,
                 ttl: int = 5,               # 消息最大跳数
                 heartbeat_interval: float = 5.0,
                 message_expiry: float = 60.0):
        """
        :param node_id: 当前节点标识
        :param network: 对P2PNode的引用（需提供 get_peers() 和 send_to_peer 方法）
        :param fanout: 每次广播随机选择的邻居数量
        :param ttl: 消息生存跳数
        :param heartbeat_interval: 定期重广播间隔（秒）
        :param message_expiry: 消息在内存中保留时间（秒）
        """
        self.node_id = node_id
        self.network = network
        self.fanout = fanout
        self.default_ttl = ttl
        self.heartbeat_interval = heartbeat_interval
        self.message_expiry = message_expiry

        self.logger = setup_logger(f"Gossip-{node_id}")

        # 已见消息缓存: {msg_hash: (timestamp, ttl_remaining)}
        self.seen_messages: Dict[str, tuple] = {}
        # 待广播队列（新生成的消息）: (msg, ttl)
        self.pending_broadcast: deque = deque()
        # 消息处理回调
        self.callbacks: Dict[MessageType, Callable] = {}

        self._running = False
        self._tasks = []

    def register_callback(self, msg_type: MessageType, callback: Callable):
        """注册消息处理函数，callback签名 async def(Message, sender_ip)"""
        self.callbacks[msg_type] = callback

    async def start(self):
        """启动Gossip服务：后台任务定期广播待发送消息"""
        self._running = True
        self._tasks.append(asyncio.create_task(self._gossip_worker()))
        self._tasks.append(asyncio.create_task(self._cleanup_worker()))
        self.logger.info("Gossip started")

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.logger.info("Gossip stopped")

    async def gossip_message(self, msg: Message, ttl: int = None):
        """
        对外接口：将消息注入Gossip网络
        会自动去重并开始广播
        """
        msg_hash = msg.compute_hash()
        if msg_hash in self.seen_messages:
            self.logger.debug(f"Message already seen: {msg_hash}")
            return

        # 记录消息
        ttl = ttl or self.default_ttl
        self.seen_messages[msg_hash] = (time.time(), ttl)

        # 本地处理（回调）
        await self._deliver_to_local(msg, None)

        # 加入待广播队列
        self.pending_broadcast.append((msg, ttl))

        self.logger.debug(f"New message queued for gossip: {msg.type.name}")

    async def _gossip_worker(self):
        """定期从队列中取出消息，并随机广播给部分邻居"""
        while self._running:
            try:
                if self.pending_broadcast:
                    # 每次广播最多处理10条，避免拥塞
                    for _ in range(min(10, len(self.pending_broadcast))):
                        msg, ttl = self.pending_broadcast.popleft()
                        await self._broadcast_to_peers(msg, ttl)
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"Gossip worker error: {e}")
                await asyncio.sleep(1)

    async def _broadcast_to_peers(self, msg: Message, ttl: int):
        """随机选择fanout个邻居，发送消息"""
        peers = self.network.get_peers() if hasattr(self.network, 'get_peers') else list(self.network.peers)
        if not peers:
            return

        # 随机选择 fanout 个节点（去重自身）
        peers = [p for p in peers if p != self.node_id]
        if len(peers) > self.fanout:
            targets = random.sample(peers, self.fanout)
        else:
            targets = peers

        # 将消息序列化一次
        serialized = msg.serialize()

        for peer in targets:
            # 附加TTL信息到payload（避免修改原消息，我们可以在消息payload中加入_gossip_ttl）
            # 简便：我们使用一个自定义字段（仅用于内部转发，接收方解析后减小TTL）
            # 为了避免污染原始payload，我们创建一个包装消息或直接修改payload（临时拷贝）
            msg_copy = Message(
                type=msg.type,
                payload=msg.payload,
                sender_id=msg.sender_id,
                timestamp=msg.timestamp,
                nonce=msg.nonce,
                signature=msg.signature
            )
            # 在payload中附加ttl信息（如果还没有的话）
            if isinstance(msg_copy.payload, dict):
                msg_copy.payload['_gossip_ttl'] = ttl - 1
            else:
                # 如果不是dict，包装成dict
                msg_copy.payload = {"_original": msg_copy.payload, "_gossip_ttl": ttl - 1}

            await self.network.send_to_peer(peer, msg_copy.serialize())

    async def _deliver_to_local(self, msg: Message, sender_ip: Optional[str]):
        """将消息交给已注册的回调处理"""
        callback = self.callbacks.get(msg.type)
        if callback:
            try:
                # 如果payload中带有_gossip_ttl，提取并移除
                if isinstance(msg.payload, dict) and '_gossip_ttl' in msg.payload:
                    original = msg.payload.get('_original')
                    if original is not None:
                        msg.payload = original
                await callback(msg, sender_ip)
            except Exception as e:
                self.logger.error(f"Callback error for {msg.type}: {e}")

    async def _cleanup_worker(self):
        """定期清理过期的已见消息"""
        while self._running:
            now = time.time()
            to_remove = []
            for h, (ts, _) in self.seen_messages.items():
                if now - ts > self.message_expiry:
                    to_remove.append(h)
            for h in to_remove:
                del self.seen_messages[h]
            if to_remove:
                self.logger.debug(f"Cleaned {len(to_remove)} expired messages")
            await asyncio.sleep(30)

    async def handle_incoming_message(self, raw_data: bytes, sender_ip: str):
        """
        网络层收到消息后调用此方法（由P2PNode转发）
        实现Gossip接收逻辑：
        - 反序列化
        - 去重
        - 减小TTL并继续广播（如果TTL>0）
        - 本地交付
        """
        try:
            msg = Message.deserialize(raw_data)
        except Exception as e:
            self.logger.warning(f"Failed to deserialize message from {sender_ip}: {e}")
            return

        msg_hash = msg.compute_hash()

        # 提取TTL（来自payload中的特殊字段）
        ttl = self.default_ttl
        if isinstance(msg.payload, dict) and '_gossip_ttl' in msg.payload:
            ttl = msg.payload['_gossip_ttl']
            # 移除内部字段避免传递给上层
            if '_original' in msg.payload:
                msg.payload = msg.payload['_original']
            else:
                # 如果只有ttl，则删除该字段
                del msg.payload['_gossip_ttl']
        else:
            ttl = self.default_ttl

        # 去重
        if msg_hash in self.seen_messages:
            self.logger.debug(f"Duplicate message from {sender_ip}: {msg_hash}")
            return

        # 记录已见
        self.seen_messages[msg_hash] = (time.time(), ttl)

        # 本地交付
        await self._deliver_to_local(msg, sender_ip)

        # 继续传播（如果还有TTL）
        if ttl > 0:
            # 为了避免循环转发，我们重新构造一个带有减一TTL的消息
            relay_msg = Message(
                type=msg.type,
                payload=msg.payload,
                sender_id=msg.sender_id,
                timestamp=msg.timestamp,
                nonce=msg.nonce,
                signature=msg.signature
            )
            if isinstance(relay_msg.payload, dict):
                relay_msg.payload['_gossip_ttl'] = ttl - 1
            else:
                relay_msg.payload = {"_original": relay_msg.payload, "_gossip_ttl": ttl - 1}
            # 随机广播
            await self._broadcast_to_peers(relay_msg, ttl - 1)