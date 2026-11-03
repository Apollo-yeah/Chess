"""对局相关 REST 接口（全部 async，均为按 game_id 分资源的风格）。"""

import logging

from app.engine.pool import EngineUnavailable
from app.game.service import GameError, get_service
from app.handlers.base_handler import BaseHandler

logger = logging.getLogger(__name__)


class GamesHandler(BaseHandler):
    """GET  /api/games      历史对局摘要列表
    POST /api/games      新建一局对局
    """

    async def get(self) -> None:
        service = get_service()
        games = await service.history()
        self.write_json({"success": True, "game_count": len(games), "games": games})

    async def post(self) -> None:
        service = get_service()
        body = self.read_json_body()
        try:
            state = await service.create(
                mode=body.get("mode", ""),
                player_color=body.get("player_color", ""),
                ai_level=body.get("ai_level", "normal"),
            )
        except GameError as exc:
            self.handle_game_error(exc)
            return
        self.write_json(
            {"success": True, "game_id": state.game_id, **state.snapshot()}, status=201
        )


class CurrentGameHandler(BaseHandler):
    """GET /api/games/current — 本进程正在进行的那一局（没有则创建）

    任意客户端进入服务时都走这里，因此大家看到并操作的是同一局。
    """

    async def get(self) -> None:
        service = get_service()
        state, _created = await service.current()
        self.write_json({"success": True, "game_id": state.game_id, **state.snapshot()})


class GameStateHandler(BaseHandler):
    """GET /api/games/{game_id} — 单局完整状态"""

    async def get(self, game_id: str) -> None:
        service = get_service()
        try:
            state = await service.require(game_id)
        except GameError as exc:
            self.handle_game_error(exc)
            return
        self.write_json({"success": True, **state.snapshot()})


class GameMoveHandler(BaseHandler):
    """POST /api/games/{game_id}/move — 玩家走棋"""

    async def post(self, game_id: str) -> None:
        body = self.read_json_body()
        service = get_service()
        try:
            state, record = await service.apply_move(game_id, body.get("move", ""))
        except GameError as exc:
            self.handle_game_error(exc)
            return
        self.write_json(
            {"success": True, "move_info": record.to_dict(), **state.snapshot()}
        )


class GameAiMoveHandler(BaseHandler):
    """POST /api/games/{game_id}/ai — 请求 AI 走棋"""

    async def post(self, game_id: str) -> None:
        body = self.read_json_body()
        service = get_service()
        try:
            state, record = await service.apply_ai_move(game_id, body.get("ai_level"))
        except EngineUnavailable as exc:
            self.write_json(
                {
                    "success": False,
                    "engine_available": False,
                    "error": f"Stockfish 引擎不可用：{exc}",
                },
                status=503,
            )
            return
        except GameError as exc:
            self.handle_game_error(exc)
            return
        self.write_json(
            {
                "success": True,
                "ai_move": record.move,
                "ai_level": state.ai_level,
                "move_info": record.to_dict(),
                **state.snapshot(),
            }
        )


class GameUndoHandler(BaseHandler):
    """POST /api/games/{game_id}/undo — 悔棋（可一次回退多着）"""

    async def post(self, game_id: str) -> None:
        body = self.read_json_body()
        service = get_service()
        try:
            state = await service.undo(game_id, body.get("plies", 1))
        except GameError as exc:
            self.handle_game_error(exc)
            return
        self.write_json({"success": True, **state.snapshot()})


class GameModeHandler(BaseHandler):
    """POST /api/games/{game_id}/mode — 设置对局模式"""

    async def post(self, game_id: str) -> None:
        body = self.read_json_body()
        service = get_service()
        try:
            state = await service.set_mode(
                game_id,
                body.get("mode", ""),
                body.get("player_color", ""),
                body.get("ai_level", "normal"),
            )
        except GameError as exc:
            self.handle_game_error(exc)
            return
        self.write_json({"success": True, **state.snapshot()})


class GameResetHandler(BaseHandler):
    """POST /api/games/{game_id}/reset — 归档当前局并开新局（返回新的 game_id）

    可选 body：``{mode, player_color, ai_level}``，用于在重置的同时切换对局模式。
    """

    async def post(self, game_id: str) -> None:
        body = self.read_json_body()
        service = get_service()
        try:
            state = await service.reset(
                game_id,
                mode=body.get("mode"),
                player_color=body.get("player_color"),
                ai_level=body.get("ai_level"),
            )
        except GameError as exc:
            self.handle_game_error(exc)
            return
        self.write_json(
            {"success": True, "game_id": state.game_id, **state.snapshot()}, status=201
        )


class GameAnalysisHandler(BaseHandler):
    """GET /api/games/{game_id}/analysis — 当前局面分析（带缓存）"""

    async def get(self, game_id: str) -> None:
        depth = self.get_query_argument("depth", None)
        service = get_service()
        try:
            analysis = await service.position_analysis(
                game_id, int(depth) if depth and depth.isdigit() else None
            )
        except EngineUnavailable as exc:
            self.write_json(
                {
                    "success": False,
                    "engine_available": False,
                    "error": f"Stockfish 引擎不可用：{exc}",
                },
                status=503,
            )
            return
        except GameError as exc:
            self.handle_game_error(exc)
            return
        self.write_json({"success": True, **analysis})
