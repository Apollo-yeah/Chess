"""对局业务编排。

* 所有变更都在**该局的锁**内完成，跨局互不阻塞。
* 服务端真正校验规则（轮次归属、走法合法性、对局是否已结束），
  不再单纯信任前端。
* 每次变更：落盘 → 推送状态 → 由 Hub 异步补推分析。
"""

import asyncio
import logging
from typing import Optional

from app.config import AI_LEVELS, DEFAULT_AI_LEVEL, POSITION_DEPTH
from app.engine.analysis import analyse_position, choose_ai_move, terminal_evaluation
from app.game.hub import GameHub, get_hub
from app.game.models import GameState, MoveRecord, now_str
from app.game.registry import GameRegistry, get_registry

logger = logging.getLogger(__name__)

VALID_MODES = {"ai", "self", ""}


class GameError(Exception):
    """业务规则错误（由 handler 转成 4xx JSON）。"""

    status = 400


class GameNotFound(GameError):
    status = 404


class GameService:
    def __init__(self, registry: Optional[GameRegistry] = None, hub: Optional[GameHub] = None):
        self._registry = registry or get_registry()
        self._hub = hub or get_hub()
        # 本进程正在进行的那一局。所有未指定 game_id 的客户端都进入这里。
        self._live_id: Optional[str] = None
        self._live_lock = asyncio.Lock()

    # --- 查询 ---
    async def history(self) -> list[dict]:
        return await self._registry.history()

    async def require(self, game_id: str) -> GameState:
        state = await self._registry.get(game_id)
        if state is None:
            raise GameNotFound(f"对局不存在：{game_id}")
        return state

    async def current(self) -> tuple[GameState, bool]:
        """返回本进程正在进行的那一局。

        还没有时创建一局。并发进入时只创建一次，之后所有客户端拿到同一 ``game_id``。
        返回 ``(state, created)``。
        """
        async with self._live_lock:
            if self._live_id:
                state = await self._registry.get(self._live_id)
                if state is not None:
                    return state, False
            state = await self._registry.create(persist=True)
            self._live_id = state.game_id
            return state, True

    async def create(
        self,
        mode: str = "",
        player_color: str = "",
        ai_level: str = DEFAULT_AI_LEVEL,
        persist: bool = True,
    ) -> GameState:
        mode = mode if mode in VALID_MODES else ""
        if mode == "ai" and player_color not in ("white", "black"):
            raise GameError("人机模式必须指定 player_color（white 或 black）")
        ai_level = ai_level if ai_level in AI_LEVELS else DEFAULT_AI_LEVEL
        state = await self._registry.create(
            mode=mode, player_color=player_color, ai_level=ai_level, persist=persist
        )
        await self._hub.broadcast_status(state)
        return state

    # --- 走棋 ---
    async def apply_move(self, game_id: str, uci: str, actor: str = "human") -> tuple[GameState, MoveRecord]:
        if not uci or not isinstance(uci, str):
            raise GameError("缺少走法参数 move")

        state = await self.require(game_id)
        async with self._registry.lock_for(game_id):
            if state.finished:
                raise GameError(f"对局已结束（{state.result}），请重置或悔棋")
            if state.mode == "ai" and actor == "human" and state.intends_ai_move():
                raise GameError("当前是 AI 回合，请等待 AI 走棋")
            record = self._push_move(state, uci, actor)
            await self._registry.persist(state)
        await self._hub.broadcast_status(state)
        return state, record

    async def apply_ai_move(
        self, game_id: str, ai_level: Optional[str] = None
    ) -> tuple[GameState, MoveRecord]:
        state = await self.require(game_id)
        level = ai_level if ai_level in AI_LEVELS else state.ai_level

        async with self._registry.lock_for(game_id):
            # 锁内串行化：避免 WS 自动走棋与手动「强制 AI 走棋」并发落两子
            if state.finished:
                raise GameError(f"对局已结束（{state.result}），请重置或悔棋")
            if state.mode == "ai" and state.player_color and state.side_to_move() == state.player_color:
                raise GameError("当前是玩家回合，AI 不应落子")
            if terminal_evaluation(state.board) is not None:
                raise GameError("当前局面已无棋可走")

            state.ai_level = level
            uci = await choose_ai_move(state.board.fen(), level)
            record = self._push_move(state, uci, "ai", ai_level=level)
            await self._registry.persist(state)

        await self._hub.broadcast_status(state)
        return state, record

    def _push_move(
        self, state: GameState, uci: str, actor: str, ai_level: Optional[str] = None
    ) -> MoveRecord:
        try:
            move = state.board.parse_uci(uci)
        except ValueError as exc:
            # python-chess 的 parse_uci 同时校验格式与合法性（非法走法也抛 ValueError）
            raise GameError(f"非法走法：{uci}") from exc
        if move not in state.board.legal_moves:
            raise GameError(f"非法走法：{uci}")

        side = "white" if state.board.turn else "black"
        san = state.board.san(move)
        state.board.push(move)

        record = MoveRecord(
            move_number=len(state.moves) + 1,
            color=side,
            move=uci,
            san=san,
            timestamp=now_str(),
            type=actor,
        )
        state.moves.append(record)
        result = state.refresh_result()
        if result != "ongoing" and not state.end_time:
            state.end_time = now_str()
        state.touch()
        return record

    # --- 悔棋 ---
    async def undo(self, game_id: str, plies: int = 1) -> GameState:
        try:
            plies = int(plies)
        except (TypeError, ValueError):
            plies = 1
        plies = max(1, min(plies, 20))

        state = await self.require(game_id)
        async with self._registry.lock_for(game_id):
            if not state.moves:
                raise GameError("暂无走棋记录，无法悔棋")
            plies = min(plies, len(state.moves))
            for _ in range(plies):
                if state.board.move_stack:
                    state.board.pop()
                state.moves.pop()

            state.refresh_result()
            if state.result == "ongoing":
                state.end_time = ""
            state.touch()
            await self._registry.persist(state)

        await self._hub.broadcast_status(state)
        return state

    # --- 模式 / 重置 ---
    async def set_mode(
        self, game_id: str, mode: str, player_color: str = "", ai_level: str = DEFAULT_AI_LEVEL
    ) -> GameState:
        if mode not in VALID_MODES:
            raise GameError(f"不支持的对局模式：{mode}")

        state = await self.require(game_id)
        async with self._registry.lock_for(game_id):
            state.mode = mode
            state.player_color = player_color if mode == "ai" else ""
            state.ai_level = ai_level if ai_level in AI_LEVELS else DEFAULT_AI_LEVEL
            state.touch()
            await self._registry.persist(state)

        await self._hub.broadcast_status(state)
        return state

    async def reset(
        self,
        game_id: str,
        mode: Optional[str] = None,
        player_color: Optional[str] = None,
        ai_level: Optional[str] = None,
    ) -> GameState:
        """归档当前局并开新局。传入模式参数即可在重置的同时切换对局模式。"""
        previous = await self.require(game_id)

        new_mode = previous.mode if mode is None else (mode if mode in VALID_MODES else "")
        if new_mode == "ai":
            color = player_color if player_color in ("white", "black") else previous.player_color
            new_color = color if color in ("white", "black") else "white"
        else:
            new_color = ""
        new_level = ai_level if ai_level in AI_LEVELS else previous.ai_level

        async with self._live_lock:
            was_live = previous.game_id == self._live_id
            await self._registry.archive(previous)
            state = await self._registry.create(
                mode=new_mode, player_color=new_color, ai_level=new_level
            )
            if was_live:
                self._live_id = state.game_id
        # 盯着旧局的连接（包括其它浏览器）跟着进入新局
        await self._hub.migrate(previous.game_id, state)
        return state

    # --- 分析 ---
    async def position_analysis(self, game_id: str, depth: Optional[int] = None) -> dict:
        state = await self.require(game_id)
        return await analyse_position(state.board.fen(), depth or POSITION_DEPTH)

    def stats(self) -> dict:
        return {
            "live_game_id": self._live_id or "",
            "registry": self._registry.stats(),
            "hub": self._hub.stats(),
        }


_service: Optional[GameService] = None


def get_service() -> GameService:
    global _service
    if _service is None:
        _service = GameService()
    return _service


async def shutdown_service() -> None:
    global _service
    hub = get_hub()
    await hub.shutdown()
    _service = None


__all__ = [
    "GameError",
    "GameNotFound",
    "GameService",
    "get_service",
    "shutdown_service",
]
