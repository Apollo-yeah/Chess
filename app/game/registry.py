"""对局注册表：按 ``game_id`` 隔离多局并行对局。

* 内存 LRU 缓存活跃对局，磁盘是权威副本（进程重启后可继续加载）。
* 每局一把 ``asyncio.Lock``：保证同一局内的并发请求串行化，
  而不同对局之间互不干扰（锁是 per-game 的，不是全局的）。
"""

import asyncio
import logging
import time
from typing import Optional

from app.config import MAX_CACHED_GAMES
from app.game.models import GameState, now_str
from app.game.storage import Storage, get_storage

logger = logging.getLogger(__name__)

# 被视为「冷」对局所需的空闲秒数（用于安全淘汰）
COLD_SECONDS = 60


class GameRegistry:
    def __init__(self, storage: Optional[Storage] = None, max_cached: int = MAX_CACHED_GAMES):
        self._storage = storage or get_storage()
        self._games: dict[str, GameState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._touched: dict[str, float] = {}
        self._max_cached = max(1, int(max_cached))

    # --- 锁 ---
    def lock_for(self, game_id: str) -> asyncio.Lock:
        lock = self._locks.get(game_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[game_id] = lock
        return lock

    # --- 读 ---
    async def get(self, game_id: str) -> Optional[GameState]:
        state = self._games.get(game_id)
        if state is not None:
            self._touched[game_id] = time.time()
            return state

        payload = await self._storage.load(game_id)
        if not payload:
            return None
        try:
            state = GameState.from_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("对局 %s 数据损坏：%s", game_id, exc)
            return None

        self._games[game_id] = state
        self._touched[game_id] = time.time()
        self._evict_if_needed()
        return state

    def peek(self, game_id: str) -> Optional[GameState]:
        return self._games.get(game_id)

    async def history(self) -> list[dict]:
        return await self._storage.list_games()

    # --- 写 ---
    async def create(
        self,
        mode: str = "",
        player_color: str = "",
        ai_level: str = "normal",
        persist: bool = True,
    ) -> GameState:
        state = GameState.new(mode=mode, player_color=player_color, ai_level=ai_level)
        self._games[state.game_id] = state
        self._touched[state.game_id] = time.time()
        if persist:
            await self._storage.save(state.to_dict())
        self._evict_if_needed()
        return state

    async def persist(self, state: GameState) -> None:
        self._touched[state.game_id] = time.time()
        await self._storage.save(state.to_dict())

    async def archive(self, state: GameState) -> None:
        """归档当前对局：未结束的标记为 abandoned 后落盘（并导出 PGN）。"""
        if state.moves:
            if not state.end_time:
                state.end_time = now_str()
            if state.result == "ongoing":
                state.result = "abandoned"
            state.touch()
            await self.persist(state)
        self.forget(state.game_id)

    def forget(self, game_id: str) -> None:
        self._games.pop(game_id, None)
        self._touched.pop(game_id, None)
        self._locks.pop(game_id, None)

    # --- 缓存管理 ---
    def _evict_if_needed(self) -> None:
        """超出上限时淘汰**冷**对局。

        只淘汰 60 秒内没有被访问过的对局：正在处理的请求一定在 ``get()``
        时刷新过时间戳，因此不会被淘汰 —— 否则淘汰与并发请求交错可能产生
        两个代表同一局的对象，导致更新丢失。
        """
        if len(self._games) <= self._max_cached:
            return

        now = time.time()
        for game_id, touched in sorted(self._touched.items(), key=lambda item: item[1]):
            if len(self._games) <= self._max_cached:
                return
            if now - touched < COLD_SECONDS:
                continue  # 最近被访问过，可能正有请求在处理
            lock = self._locks.get(game_id)
            if lock is not None and lock.locked():
                continue
            self._games.pop(game_id, None)
            self._touched.pop(game_id, None)
            self._locks.pop(game_id, None)

        if len(self._games) > self._max_cached:
            logger.debug(
                "缓存 %s 局（上限 %s）：活跃对局过多，暂不淘汰",
                len(self._games),
                self._max_cached,
            )

    def stats(self) -> dict:
        return {
            "cached": len(self._games),
            "max_cached": self._max_cached,
            "locked": sum(1 for lock in self._locks.values() if lock.locked()),
        }


_registry: Optional[GameRegistry] = None


def get_registry() -> GameRegistry:
    global _registry
    if _registry is None:
        _registry = GameRegistry()
    return _registry
