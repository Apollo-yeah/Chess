"""对局 WebSocket：按 ``game_id`` 订阅，两段式推送（状态 → 分析）。

客户端消息协议::

    {"action": "refresh"}                   重新推送当前局状态
    {"action": "subscribe", "game_id": "x"}  切换订阅另一局
    {"action": "ping"}                       心跳

未携带 ``game_id``（或指定的对局已不存在）时，连接进入**本进程正在进行的那一局**，
而不是各自新开一局。重置后服务端会把这些连接迁到新局。

服务端消息协议::

    {"type": "hello",           "game_id", "adopted", "status"}
    {"type": "status_update",   "status", "version"}
    {"type": "analysis_update", "analysis", "version", "fen"}
    {"type": "error",           "message"}
    {"type": "pong"}
"""

import json
import logging
import urllib.parse

import tornado.websocket

from app.config import CORS_ORIGINS
from app.game.hub import get_hub
from app.game.service import GameError, get_service

logger = logging.getLogger(__name__)


class GameWebSocketHandler(tornado.websocket.WebSocketHandler):
    game_id: str = ""

    # --- 安全 ---
    def _forwarded_hosts(self) -> set[str]:
        """反代可能改写 Host（例如 Nginx 的 ``$host`` 会丢掉端口），因此两个头都看。"""
        hosts: set[str] = set()
        for header in ("X-Forwarded-Host", "Host"):
            value = self.request.headers.get(header)
            if value:
                hosts.add(value.split(",")[0].strip().lower())
        return hosts

    def check_origin(self, origin: str) -> bool:
        """只接受同源连接（或显式白名单），替代旧的 ``return True``。

        防御目标是跨站 WebSocket 劫持（其它站点借用浏览器发起连接）。
        比分两条：
        1. Origin 的 ``host:port`` 与反向代理转发的主机完全一致 → 通过；
        2. 否则退化为**主机名**比较（忽略端口）——因为反代常把端口丢掉
           （``proxy_set_header Host $host``），而端口差异并不构成跨站威胁。
        """
        if not origin:
            return True  # 非浏览器客户端（无 Origin），不受 CSRF 影响
        if "*" in CORS_ORIGINS or origin in CORS_ORIGINS:
            return True

        parsed = urllib.parse.urlparse(origin)
        netloc = (parsed.netloc or "").lower()
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False

        expected = self._forwarded_hosts()
        if netloc and netloc in expected:
            return True

        expected_hostnames = set()
        for entry in expected:
            name = urllib.parse.urlparse(f"//{entry}").hostname
            if name:
                expected_hostnames.add(name.lower())
        return hostname in expected_hostnames

    # 注意：不要覆盖 ``get()`` —— Tornado 正是在该方法里完成 WebSocket 握手，
    # 覆盖它会让所有连接握手失败（非 WebSocket 请求的 400 由 Tornado 默认处理）。

    # --- 生命周期 ---
    async def open(self, *args, **kwargs) -> None:
        requested = self.get_query_argument("game_id", None)
        service = get_service()
        hub = get_hub()
        self.game_id = ""

        state = None
        if requested:
            try:
                state = await service.require(requested)
            except GameError:
                state = None

        created = False
        if state is None:
            # 未指定、或指定了已经不存在的对局：进入本进程正在进行的那一局
            try:
                state, created = await service.current()
            except Exception as exc:  # noqa: BLE001
                logger.warning("WebSocket 加入当前对局失败：%s", exc)
                self.close(1011, "服务器无法初始化对局")
                return

        self.game_id = state.game_id
        hub.subscribe(state.game_id, self)
        self.write_message(
            {
                "type": "hello",
                "game_id": state.game_id,
                "adopted": created,
                "status": state.snapshot(),
                "version": state.version,
            }
        )
        hub.schedule_analysis(state.game_id)

    def on_close(self) -> None:
        get_hub().unsubscribe_handler(self)

    async def on_message(self, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            self.write_message({"type": "error", "message": "消息必须是 JSON"})
            return
        if not isinstance(data, dict):
            self.write_message({"type": "error", "message": "消息必须是 JSON 对象"})
            return

        action = data.get("action")
        hub = get_hub()
        service = get_service()

        if action == "ping":
            self.write_message({"type": "pong"})
            return

        if action == "subscribe":
            target = (data.get("game_id") or "").strip()
            if not target:
                self.write_message({"type": "error", "message": "缺少 game_id"})
                return
            try:
                state = await service.require(target)
            except GameError as exc:
                self.write_message({"type": "error", "message": str(exc)})
                return
            hub.subscribe(state.game_id, self)
            self.game_id = state.game_id
            self.write_message(
                {
                    "type": "hello",
                    "game_id": state.game_id,
                    "adopted": False,
                    "status": state.snapshot(),
                    "version": state.version,
                }
            )
            hub.schedule_analysis(state.game_id)
            return

        if action in (None, "refresh"):
            if not self.game_id:
                self.write_message({"type": "error", "message": "尚未订阅对局"})
                return
            try:
                state = await service.require(self.game_id)
            except GameError as exc:
                self.write_message({"type": "error", "message": str(exc)})
                return
            self.write_message(
                {
                    "type": "status_update",
                    "status": state.snapshot(),
                    "version": state.version,
                }
            )
            hub.schedule_analysis(state.game_id)
            return

        self.write_message({"type": "error", "message": f"未知指令：{action}"})

    # --- 错误 ---
    def write_message(self, message, binary: bool = False) -> None:  # type: ignore[override]
        """推送失败（连接已断开）时不再抛异常打断广播。"""
        try:
            return super().write_message(message, binary)
        except tornado.websocket.WebSocketClosedError:
            get_hub().unsubscribe_handler(self)
            return None


__all__ = ["GameWebSocketHandler"]
