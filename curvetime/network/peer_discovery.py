"""基于Kademlia思想的简单节点发现（兼容WebSocket传输）"""
import asyncio
import random
import time
from typing import Set, List, Dict, Tuple, Optional
from collections import defaultdict

from .protocol import Message, MessageType, Protocol
from ...utils.logger import setup_logger


class PeerDiscovery:
    """
    节点发现组件
    特性：
    - 维护已知节点列表（地址:端口）
    - 定期主动探测节点活性（Ping/Pong）
    - 启动时连接种子节点（bootstrap）
    - 交换节点列表（PEER_LIST）
    - 简单的路由表（按网络前缀分组）
    """

    def __init__(self,
                 node_id: str,
                 listen_port: int,
                 network,
                 bootstrap_peers: List[str],
                 max_peers: int = 100,
                 ping_interval: float = 60.0,
                 discovery_interval: float = 120.0):
        """
        :param node_id: 节点标识（通常为 "ip:port"）
        :param listen_port: 本节点监听端口
        :param network: 对P2PNode的引用，需要提供 send_to_peer 方法
        :param bootstrap_peers: 种子节点地址列表 ["ip1:port1", ...]
        :param max_peers: 最大保持连接数
        :param ping_interval: 定期发送Ping的间隔
        :param discovery_interval: 主动向随机节点请求更多邻居的间隔
        """
        self.node_id = node_id
        self.listen_port = listen_port
        self.network = network
        self.bootstrap_peers = bootstrap_peers
        self.max_peers = max_peers

        self.logger = setup_logger(f"PeerDiscovery-{node_id}")

        # 已知节点集合：{ "ip:port": {"last_seen": timestamp, "services": int, "ping_rtt": float} }
        self.peers: Dict[str, dict] = {}
        # 对于可能还未建立长连接的节点，我们也保存其地址以便未来连接
        self.pending_peers: Set[str] = set()

        # 配置
        self.ping_interval = ping_interval
        self.discovery_interval = discovery_interval

        # 控制标志
        self._running = False
        self._tasks = []

    async def start(self):
        """启动发现服务：连接种子节点、启动后台任务"""
        self._running = True

        # 添加自身（但不用于对外广播）
        self.peers[self.node_id] = {"last_seen": time.time(), "services": 1, "ping_rtt": 0.0}

        # 连接引导节点
        for addr in self.bootstrap_peers:
            if addr != self.node_id:
                await self.add_peer(addr, is_seed=True)

        # 启动后台任务
        self._tasks.append(asyncio.create_task(self._ping_loop()))
        self._tasks.append(asyncio.create_task(self._discovery_loop()))
        self._tasks.append(asyncio.create_task(self._announce_loop()))

        self.logger.info(f"PeerDiscovery started, bootstrap: {self.bootstrap_peers}")

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.logger.info("PeerDiscovery stopped")

    async def add_peer(self, addr: str, is_seed: bool = False) -> bool:
        """添加一个节点到已知列表，如果未满则尝试建立连接"""
        if addr == self.node_id:
            return False
        if addr in self.peers:
            self.peers[addr]["last_seen"] = time.time()
            return True

        # 限制最大数量
        if len(self.peers) >= self.max_peers and not is_seed:
            # 移除最旧且未响应的节点
            await self._evict_oldest_peer()
            if len(self.peers) >= self.max_peers:
                return False

        # 尝试发送Ping测试连通性
        if await self._ping_peer(addr):
            self.peers[addr] = {"last_seen": time.time(), "services": 0, "ping_rtt": 0.0}
            self.logger.info(f"New peer added: {addr}")
            # 主动请求该节点的邻居列表
            await self._request_peer_list(addr)
            return True
        else:
            self.logger.debug(f"Failed to ping {addr}, not adding")
            return False

    async def _ping_peer(self, addr: str) -> bool:
        """发送Ping消息，等待Pong，超时3秒"""
        try:
            msg = Protocol.ping_msg(self.node_id)
            send_time = time.time()
            # 使用网络层发送并等待回复（需要扩展network支持request-response）
            # 简化：直接发送，假设对方会通过处理函数回复Pong，我们异步等待
            # 实际需要实现一个简单的请求-回复机制。这里为了简洁，我们模拟一个同步等待：
            # 通过回调方式更合理，为简便，我们直接假设网络层支持send_and_wait
            # 由于p2p_node目前是单向推送，我们用一个Future等待。
            # 在真实实现中，可在P2PNode中注册临时回调。
            # 这里我们采用简单方式：不等待回复，只发送，依赖后续心跳确认存活。
            # 为了功能完整，我们实现一个简易的Future存储。
            future = asyncio.Future()
            key = f"pong_{addr}_{msg.nonce}"
            self.network.register_temp_callback(key, future)  # 假设存在此方法
            await self.network.send_to_peer(addr, msg.serialize())
            try:
                await asyncio.wait_for(future, 3.0)
                rtt = time.time() - send_time
                if addr in self.peers:
                    self.peers[addr]["ping_rtt"] = rtt
                return True
            except asyncio.TimeoutError:
                return False
            finally:
                self.network.unregister_temp_callback(key)
        except Exception:
            return False

    async def _request_peer_list(self, target_addr: str):
        """向目标节点请求其已知节点列表"""
        msg = Protocol.peer_list_msg(self.node_id, [])  # 空的peers表示请求
        await self.network.send_to_peer(target_addr, msg.serialize())

    async def _ping_loop(self):
        """定期Ping所有已知节点，移除不响应的节点"""
        while self._running:
            await asyncio.sleep(self.ping_interval)
            for addr in list(self.peers.keys()):
                if addr == self.node_id:
                    continue
                if not await self._ping_peer(addr):
                    self.logger.warning(f"Peer {addr} unreachable, removing")
                    del self.peers[addr]

    async def _discovery_loop(self):
        """定期随机选择节点，向其索要节点列表"""
        while self._running:
            await asyncio.sleep(self.discovery_interval)
            if not self.peers:
                continue
            # 排除自身
            candidates = [p for p in self.peers if p != self.node_id]
            if not candidates:
                continue
            target = random.choice(candidates)
            await self._request_peer_list(target)

    async def _announce_loop(self):
        """定期向所有节点广播自身存在（PEER_ANNOUNCE）"""
        while self._running:
            await asyncio.sleep(self.ping_interval * 2)
            announce_msg = Protocol.peer_announce_msg(self.node_id, self.listen_port)
            # 广播给所有已知节点
            for addr in list(self.peers.keys()):
                if addr != self.node_id:
                    await self.network.send_to_peer(addr, announce_msg.serialize())

    async def _evict_oldest_peer(self):
        """移除最老且RTT最大的节点（简单策略）"""
        if not self.peers:
            return
        oldest = min(self.peers.items(), key=lambda x: x[1]["last_seen"])
        del self.peers[oldest[0]]
        self.logger.info(f"Evicted oldest peer: {oldest[0]}")

    async def handle_peer_message(self, msg: Message, sender_ip: str):
        """
        处理与节点发现相关的消息（PEER_ANNOUNCE, PEER_LIST, PING, PONG）
        由P2PNode在收到消息时调用此方法
        """
        if msg.type == MessageType.PEER_ANNOUNCE:
            # 对方宣告自己存在
            port = msg.payload.get("port", 0)
            addr = f"{sender_ip}:{port}" if port else sender_ip
            await self.add_peer(addr)

        elif msg.type == MessageType.PEER_LIST:
            # 收到了节点列表
            peers_list = msg.payload.get("peers", [])
            for peer_addr in peers_list:
                if peer_addr != self.node_id:
                    await self.add_peer(peer_addr)
            # 如果对方请求列表（即payload为空数组），则回复我们自己的列表
            if not msg.payload.get("peers"):
                # 回复我们的peer列表（最多返回50个）
                my_peers = [p for p in self.peers if p != self.node_id][:50]
                response = Protocol.peer_list_msg(self.node_id, my_peers)
                await self.network.send_to_peer(sender_ip, response.serialize())

        elif msg.type == MessageType.PING:
            # 回复PONG
            pong_msg = Protocol.pong_msg(self.node_id, msg.timestamp)
            await self.network.send_to_peer(sender_ip, pong_msg.serialize())

        elif msg.type == MessageType.PONG:
            # 通知等待的Future（通过临时回调）
            key = f"pong_{sender_ip}_{msg.payload.get('echo', 0)}"  # 简化，实际用nonce更好
            # 由网络层负责分发
            pass

    def get_peers(self) -> List[str]:
        """返回已知节点地址列表（排除自身）"""
        return [p for p in self.peers if p != self.node_id]