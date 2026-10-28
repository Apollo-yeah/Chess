"""推送中心：按 ``game_id`` 分组的 WebSocket 订阅与两段式推送。

关键改进（相对旧实现）
--------------------
* 订阅按对局分组：一次走棋只通知**该局**的订阅者，不再全服广播。
* 分析结果**按局面算一次**并被所有订阅者共享（旧实现是每个客户端各跑 3 次引擎）。
* 两段式推送：状态先发（微秒级），分析算完后再补发一条 ``analysis_update``，
  因此引擎搜索永远不会拖慢状态同步。
* 局面已变时丢弃陈旧分析结果（按 ``version`` 校验），避免界面回跳。
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Optional

from app.config import BROADCAST_DEPTH
from app.engine.analysis import analyse_position
from app.engine.pool import EngineUnavailable
from app.game.models import GameState, now_str
from app.game.registry import GameRegistry, get_registry

logger = logging.getLogger(__name__)


class GameHub:
    def __init__(self, registry: Optional[GameRegistry] = None):
        self._registry = registry or get_registry()
        self._subscribers: dict[str, set[Any]] = defaultdict(set)
        self._analysis_tasks: dict[str, asyncio.Task] = {}
        self._handlers: dict[Any, str] = {}

    # --- 订阅管理 ---
    def subscribe(self, game_id: str, handler: Any) -> None:
        self.unsubscribe_handler(handler)
        self._subscribers[game_id].add(handler)
        self._handlers[handler] = game_id

    def unsubscribe_handler(self, handler: Any) -> None:
        game_id = self._handlers.pop(handler, None)
        if game_id is None:
            return
        group = self._subscribers.get(game_id)
        if group is not None:
            group.discard(handler)
            if not group:
                self._subscribers.pop(game_id, None)

    def subscriber_count(self, game_id: Optional[str] = None) -> int:
        if game_id is None:
            return sum(len(group) for group in self._subscribers.values())
        return len(self._subscribers.get(game_id, ()))

    # --- 发送 ---
    async def _send_to_game(self, game_id: str, payload: dict) -> int:
        group = list(self._subscribers.get(game_id, ()))
        if not group:
            return 0
        sent = 0
        for handler in group:
            try:
                handler.write_message(payload)
                sent += 1
            except Exception as exc:  # 连接已断开等
                logger.debug("推送失败，移除订阅者：%s", exc)
                self.unsubscribe_handler(handler)
        return sent

    async def migrate(self, old_game_id: str, state: GameState) -> int:
        """把仍盯着旧局的连接改挂到新局，并立刻推送新局面。

        重置会换成新的 ``game_id``。若不迁移，其它客户端会继续停在已经归档的那一局。
        """
        group = self._subscribers.pop(old_game_id, set())
        new_id = state.game_id
        for handler in list(group):
            self._handlers[handler] = new_id
            if hasattr(handler, "game_id"):
                handler.game_id = new_id
        if group:
            self._subscribers[new_id].update(group)

        previous = self._analysis_tasks.pop(old_game_id, None)
        if previous is not None and not previous.done():
            previous.cancel()
        return await self.broadcast_status(state)

    async def broadcast_status(self, state: GameState, *, include_analysis: bool = True) -> int:
        payload = {
            "type": "status_update",
            "status": state.snapshot(),
            "version": state.version,
            "timestamp": now_str(),
        }
        sent = await self._send_to_game(state.game_id, payload)
        if include_analysis:
            self.schedule_analysis(state.game_id)
        return sent

    async def send_analysis(self, game_id: str, analysis: dict, version: int, fen: str) -> int:
        return await self._send_to_game(
            game_id,
            {
                "type": "analysis_update",
                "analysis": analysis,
                "version": version,
                "fen": fen,
                "timestamp": now_str(),
            },
        )

    # --- 分析调度 ---
    def schedule_analysis(self, game_id: str) -> None:
        """为一个局面安排分析：同一局只保留最新一次，旧任务取消。"""
        state = self._registry.peek(game_id)
        if state is None or not self.subscriber_count(game_id):
            return

        previous = self._analysis_tasks.get(game_id)
        if previous is not None and not previous.done():
            previous.cancel()

        task = asyncio.create_task(self._analyse_and_push(game_id, state.board.fen(), state.version))
        self._analysis_tasks[game_id] = task

    async def _analyse_and_push(self, game_id: str, fen: str, version: int) -> None:
        try:
            analysis = await analyse_position(fen, BROADCAST_DEPTH, with_best_moves=True)
        except asyncio.CancelledError:
            raise
        except EngineUnavailable as exc:
            analysis = {"success": False, "engine_available": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - 分析失败不能影响对局
            logger.warning("局面分析失败：%s", exc)
            analysis = {"success": False, "error": str(exc)}

        current = self._registry.peek(game_id)
        if current is not None and current.version != version:
            return  # 局面已变化，本次分析作废

        await self.send_analysis(game_id, analysis, version, fen)

    async def shutdown(self) -> None:
        for task in list(self._analysis_tasks.values()):
            if not task.done():
                task.cancel()
        tasks = [task for task in self._analysis_tasks.values() if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._analysis_tasks.clear()
        self._subscribers.clear()
        self._handlers.clear()

    def stats(self) -> dict:
        return {
            "subscribers": self.subscriber_count(),
            "games": len(self._subscribers),
            "analysis_tasks": sum(1 for task in self._analysis_tasks.values() if not task.done()),
        }


_hub: Optional[GameHub] = None


def get_hub() -> GameHub:
    global _hub
    if _hub is None:
        _hub = GameHub()
    return _hub
