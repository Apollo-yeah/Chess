"""持久化层：每局一个 JSON 文件，终局时额外导出 PGN。

所有磁盘 I/O 都通过专用线程池执行，不阻塞 IOLoop。
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import chess
import chess.pgn
from tornado.ioloop import IOLoop

from app.config import GAME_DATA_DIR, PGN_SAVE_DIR, ensure_dirs

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="storage")

RESULT_TO_PGN = {
    "white_win": "1-0",
    "black_win": "0-1",
    "draw": "1/2-1/2",
    "abandoned": "*",
    "ongoing": "*",
}

_UNSAFE = re.compile(r"[^0-9A-Za-z._-]+")


def _safe_name(value: str) -> str:
    """文件名安全化：时间戳里的冒号在 Windows / 部分卷上非法。"""
    return _UNSAFE.sub("-", value).strip("-") or "game"


class Storage:
    def __init__(self, data_dir=GAME_DATA_DIR, pgn_dir=PGN_SAVE_DIR, executor=_EXECUTOR):
        self.data_dir = data_dir
        self.pgn_dir = pgn_dir
        self._executor = executor

    # --- 路径 ---
    def game_path(self, game_id: str) -> str:
        return os.path.join(self.data_dir, f"{game_id}.json")

    # --- 同步实现（仅在 executor 线程中调用）---
    def _load_sync(self, game_id: str) -> Optional[dict]:
        path = self.game_path(game_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("对局 %s 读取失败：%s", game_id, exc)
            return None

    def _save_sync(self, payload: dict) -> str:
        path = self.game_path(payload["game_id"])
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        if payload.get("result") not in ("ongoing", "", None) and payload.get("moves"):
            self._export_pgn_sync(payload)
        return path

    def _list_sync(self) -> list[dict]:
        if not os.path.isdir(self.data_dir):
            return []
        entries: list[tuple[float, dict]] = []
        for filename in os.listdir(self.data_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.data_dir, filename)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            payload = self._load_sync(filename[:-5])
            if not payload:
                continue
            entries.append((mtime, self._summarize(payload)))
        entries.sort(key=lambda item: item[0], reverse=True)
        return [summary for _, summary in entries]

    @staticmethod
    def _summarize(payload: dict) -> dict:
        moves = payload.get("moves") or []
        return {
            "game_id": payload.get("game_id", ""),
            "start_time": payload.get("start_time", ""),
            "end_time": payload.get("end_time", ""),
            "mode": payload.get("mode", ""),
            "player_color": payload.get("player_color", ""),
            "ai_level": payload.get("ai_level", ""),
            "result": payload.get("result", ""),
            "total_moves": len(moves),
        }

    # --- PGN 导出 ---
    def _export_pgn_sync(self, payload: dict) -> Optional[str]:
        moves = payload.get("moves") or []
        if not moves:
            return None

        game_id = payload.get("game_id", "unknown")
        start_time = payload.get("start_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        end_time = payload.get("end_time") or ""
        mode = (payload.get("mode") or "").strip()
        ai_level = payload.get("ai_level") or "normal"
        player_color = (payload.get("player_color") or "").strip()
        ai_name = f"AI ({ai_level})"

        def first_move_type(color: str) -> str:
            for move in moves:
                if move.get("color") == color:
                    return move.get("type") or ""
            return ""

        if mode == "ai" and player_color in ("white", "black"):
            # 元信息齐全：玩家执 player_color，另一侧是 AI
            white_player = "Human" if player_color == "white" else ai_name
            black_player = "Human" if player_color == "black" else ai_name
        elif mode in ("self", "human_vs_human") or (not mode and all(
            (move.get("type") or "human") == "human" for move in moves
        )):
            white_player = black_player = "Human"
        elif not mode and all((move.get("type") or "") == "ai" for move in moves):
            white_player = black_player = ai_name
        else:
            # 旧数据（缺 mode）：按双方各自第一条走法的类型粗略推断
            white_player = ai_name if first_move_type("white") == "ai" else "Human"
            black_player = ai_name if first_move_type("black") == "ai" else "Human"

        game_mode = mode or "self"

        pgn_game = chess.pgn.Game()
        pgn_game.headers.update(
            {
                "Event": f"Chess Game ({game_mode} mode)",
                "Site": "Local Game",
                "Date": start_time.split()[0].replace("-", ".") if start_time else "",
                "Round": "1",
                "White": white_player,
                "Black": black_player,
                "Result": RESULT_TO_PGN.get(payload.get("result", "ongoing"), "*"),
                "StartTime": start_time,
                "EndTime": end_time,
                "AILevel": ai_level,
                "GameID": game_id,
            }
        )

        board = chess.Board()
        node = pgn_game
        for move_info in moves:
            uci = (move_info.get("move") or "").strip()
            if not uci:
                continue
            try:
                move = board.parse_uci(uci)
            except ValueError:
                continue
            if move not in board.legal_moves:
                continue
            node = node.add_variation(move)
            board.push(move)

        filename = f"{_safe_name(start_time)}_{game_id[:8]}.pgn"
        path = os.path.join(self.pgn_dir, filename)
        with open(path, "w", encoding="utf-8") as handle:
            pgn_game.accept(chess.pgn.FileExporter(handle))
        logger.info("PGN 已导出：%s", path)
        return path

    # --- 异步包装 ---
    async def _run(self, func, *args):
        return await IOLoop.current().run_in_executor(self._executor, func, *args)

    async def load(self, game_id: str) -> Optional[dict]:
        return await self._run(self._load_sync, game_id)

    async def save(self, payload: dict) -> str:
        return await self._run(self._save_sync, payload)

    async def list_games(self) -> list[dict]:
        return await self._run(self._list_sync)


_storage: Optional[Storage] = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        ensure_dirs()
        _storage = Storage()
    return _storage


def storage_info() -> dict:
    storage = get_storage()
    return {
        "data_dir": str(storage.data_dir),
        "pgn_dir": str(storage.pgn_dir),
        "executor": "thread",
    }


__all__ = ["Storage", "get_storage", "storage_info", "RESULT_TO_PGN"]
