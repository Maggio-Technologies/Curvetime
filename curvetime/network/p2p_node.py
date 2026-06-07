"""P2P网络节点：基于WebSocket的通信实现，集成Gossip和节点发现"""
import asyncio
import json
import time
import uuid
from typing import Set, Dict, Callable, Optional, List, Any
from enum import IntEnum
import websockets
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from .protocol import Message, MessageType, Protocol
from .gossip import Gossip
from .peer_discovery import PeerDiscovery
from ...utils.logger import setup_logger


class P2PNode:
    """
    P2P 网络节点
    - 管理 WebSocket 连接
    - 转发消息给 Gossip 和 PeerDiscovery
    - 提供 send_to_peer 和 broadcast 接口
    - 临时回调支持（用于请求-响应模式）
    """

    def __init__(self,
                 host: str = "0.0.0.0",
                 port: int = 9000,
                 bootstrap_peers: List[str] = None,
                 max_peers: int = 100,
                 gossip_fanout: int = 3,
                 ping_interval: float = 60.0):
        """
        :param host: 监听地址
        :param port: 监听端口
        :param bootstrap_peers: 种子节点列表，格式 ["ip:port", ...]
        :param max_peers: 最大维持连接数
        :param gossip_fanout: Gossip 扇出数
        :param ping_interval: 节点发现Ping间隔
        """
        self.host = host
        self.port = port
        self.bootstrap_peers = bootstrap_peers or []
        self.max_peers = max_peers
        self.node_id = f"{self.host}:{self.port}"  # 简化ID，实际可用公网IP

        self.logger = setup_logger(f"P2PNode-{self.node_id}")

        # WebSocket 服务器和活动连接
        self.websocket_server = None
        self.active_connections: Dict[str, websockets.WebSocketServerProtocol] = {}  # peer_id -> ws

        # 组件
        self.discovery = PeerDiscovery(
            node_id=self.node_id,
            listen_port=self.port,
            network=self,                     # 传入自身引用
            bootstrap_peers=self.bootstrap_peers,
            max_peers=max_peers,
            ping_interval=ping_interval,
            discovery_interval=120.0
        )
        self.gossip = Gossip(
            node_id=self.node_id,
            network=self,
            fanout=gossip_fanout,
            heartbeat_interval=5.0,
            message_expiry=60.0
        )

        # 临时回调：用于等待特定响应
        self._temp_callbacks: Dict[str, asyncio.Future] = {}
        self._callback_lock = asyncio.Lock()

        # 运行标志
        self._running = False
        self._server_task = None

    # ------------------ 生命周期 ------------------
    async def start(self):
        """启动节点：启动WebSocket服务器、Gossip、节点发现"""
        self._running = True

        # 启动 WebSocket 服务器
        self.websocket_server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            max_size=2**23,      # 8MB 消息上限
            ping_interval=20,
            ping_timeout=60
        )
        self.logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")

        # 启动内部组件
        await self.discovery.start()
        await self.gossip.start()

        # 连接种子节点（PeerDiscovery 已经做了，但这里确保连接建立）
        for addr in self.bootstrap_peers:
            await self.connect_to_peer(addr)

        self.logger.info(f"P2PNode {self.node_id} started")

    async def stop(self):
        """优雅停止节点"""
        self._running = False
        self.logger.info("Stopping P2PNode...")

        # 关闭所有 WebSocket 连接
        for peer_id, ws in list(self.active_connections.items()):
            try:
                await ws.close()
            except:
                pass
        self.active_connections.clear()

        # 停止组件
        await self.gossip.stop()
        await self.discovery.stop()

        # 关闭服务器
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()

        # 取消所有等待的回调
        async with self._callback_lock:
            for fut in self._temp_callbacks.values():
                if not fut.done():
                    fut.set_exception(Exception("Node stopping"))
            self._temp_callbacks.clear()

        self.logger.info("P2PNode stopped")

    # ------------------ 连接管理 ------------------
    async def _handle_client(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """处理入站 WebSocket 连接"""
        remote_addr = websocket.remote_address[0] if websocket.remote_address else "unknown"
        peer_id = f"{remote_addr}:{self.port}"   # 简化，实际应该从消息中获取
        self.logger.debug(f"New connection from {remote_addr}")

        # 如果连接数超限，拒绝
        if len(self.active_connections) >= self.max_peers:
            self.logger.warning(f"Max peers reached, rejecting {remote_addr}")
            await websocket.close(code=1008, reason="Too many peers")
            return

        self.active_connections[peer_id] = websocket

        try:
            async for raw_msg in websocket:
                await self._process_incoming_message(raw_msg, remote_addr)
        except ConnectionClosedOK:
            self.logger.debug(f"Connection closed normally: {peer_id}")
        except ConnectionClosedError as e:
            self.logger.warning(f"Connection closed with error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error handling client {peer_id}: {e}")
        finally:
            # 移除断开的连接
            self.active_connections.pop(peer_id, None)
            self.logger.info(f"Removed peer {peer_id}, active: {len(self.active_connections)}")

    async def connect_to_peer(self, peer_addr: str) -> bool:
        """
        主动连接到另一个节点
        :param peer_addr: 格式 "ip:port"
        :return: 是否连接成功
        """
        if peer_addr in self.active_connections:
            return True
        if peer_addr == self.node_id:
            return False

        try:
            # 尝试建立 WebSocket 连接
            ws = await websockets.connect(f"ws://{peer_addr}", ping_interval=20, ping_timeout=60)
            self.active_connections[peer_addr] = ws
            self.logger.info(f"Connected to peer {peer_addr}")
            # 启动一个后台任务接收该连接上的消息
            asyncio.create_task(self._handle_outbound_connection(peer_addr, ws))
            return True
        except Exception as e:
            self.logger.warning(f"Failed to connect to {peer_addr}: {e}")
            return False

    async def _handle_outbound_connection(self, peer_addr: str, websocket: websockets.WebSocketClientProtocol):
        """处理出站连接的消息接收循环"""
        try:
            async for raw_msg in websocket:
                # 提取远程IP
                remote_ip = websocket.remote_address[0] if websocket.remote_address else peer_addr.split(':')[0]
                await self._process_incoming_message(raw_msg, remote_ip)
        except ConnectionClosedOK:
            self.logger.debug(f"Outbound connection closed: {peer_addr}")
        except Exception as e:
            self.logger.error(f"Error in outbound connection {peer_addr}: {e}")
        finally:
            self.active_connections.pop(peer_addr, None)
            await websocket.close()

    async def _process_incoming_message(self, raw_data: bytes, sender_ip: str):
        """处理收到的原始消息（先交给节点发现和Gossip）"""
        # 先尝试解析为通用Message
        try:
            msg = Message.deserialize(raw_data)
        except Exception as e:
            self.logger.warning(f"Invalid message from {sender_ip}: {e}")
            return

        # 处理节点发现相关消息（PING/PONG/PEER_LIST等）
        await self.discovery.handle_peer_message(msg, sender_ip)

        # 处理通过Gossip传播的消息（会触发回调）
        await self.gossip.handle_incoming_message(raw_data, sender_ip)

        # 处理临时回调（例如PONG的响应）
        if msg.type == MessageType.PONG:
            # 构造回调key（基于发送者IP和消息中的时间戳）
            # 实际使用 nonce 更准确，这里简化用 timestamp
            callback_key = f"pong_{sender_ip}_{msg.payload.get('echo', 0)}"
            async with self._callback_lock:
                future = self._temp_callbacks.pop(callback_key, None)
                if future and not future.done():
                    future.set_result(msg)

    # ------------------ 消息发送接口 ------------------
    async def send_to_peer(self, peer_addr: str, data: bytes) -> bool:
        """向指定节点发送原始字节数据"""
        ws = self.active_connections.get(peer_addr)
        if not ws:
            # 尝试重新连接
            if await self.connect_to_peer(peer_addr):
                ws = self.active_connections.get(peer_addr)
            else:
                return False
        try:
            await ws.send(data)
            return True
        except Exception as e:
            self.logger.error(f"Send to {peer_addr} failed: {e}")
            # 移除失效连接
            self.active_connections.pop(peer_addr, None)
            return False

    async def broadcast_message(self, msg_type: MessageType, payload: dict, ttl: int = 5):
        """
        向全网广播消息（通过Gossip，不直接发送给所有连接）
        """
        msg = Message(
            type=msg_type,
            payload=payload,
            sender_id=self.node_id,
            timestamp=time.time(),
            nonce=int(time.time() * 1000) % (2**32)
        )
        # 注入Gossip
        await self.gossip.gossip_message(msg, ttl)

    async def direct_send_to_all(self, data: bytes):
        """直接发送给所有已连接的节点（不经过Gossip），慎用"""
        tasks = []
        for peer_addr, ws in self.active_connections.items():
            tasks.append(self.send_to_peer(peer_addr, data))
        await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------ 临时回调（用于请求-响应）------------------
    def register_temp_callback(self, key: str, future: asyncio.Future):
        """注册一个等待响应的 Future，稍后由消息处理触发"""
        async def _register():
            async with self._callback_lock:
                self._temp_callbacks[key] = future
        asyncio.create_task(_register())

    def unregister_temp_callback(self, key: str):
        """取消注册"""
        async def _unregister():
            async with self._callback_lock:
                self._temp_callbacks.pop(key, None)
        asyncio.create_task(_unregister())

    # ------------------ 获取状态 ------------------
    def get_peers(self) -> List[str]:
        """返回当前连接的对等节点地址列表"""
        return list(self.active_connections.keys())

    def get_peer_count(self) -> int:
        return len(self.active_connections)

    def is_running(self) -> bool:
        return self._running