"""单局对局状态。

每局棋拥有自己的 ``chess.Board``、走法记录与元信息，彼此完全隔离；
``version`` 每次变更自增，供 WebSocket 判断推送是否为陈旧数据。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import chess

DEFAULT_AI_LEVEL = "normal"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def evaluate_result(board: chess.Board) -> str:
    """判断对局结果（与 UI 的 white_win / black_win / draw / ongoing 对齐）。"""
    if board.is_checkmate():
        return "black_win" if board.turn else "white_win"
    if (
        board.is_stalemate()
        or board.is_insufficient_material()
        or board.is_seventyfive_moves()
        or board.is_fivefold_repetition()
    ):
        return "draw"
    return "ongoing"


@dataclass
class MoveRecord:
    move_number: int
    color: str  # white | black
    move: str  # UCI
    san: str = ""
    timestamp: str = field(default_factory=now_str)
    type: str = "human"  # human | ai

    def to_dict(self) -> dict:
        return {
            "move_number": self.move_number,
            "color": self.color,
            "move": self.move,
            "san": self.san,
            "timestamp": self.timestamp,
            "type": self.type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MoveRecord":
        return cls(
            move_number=int(data.get("move_number") or 0),
            color=data.get("color") or "",
            move=data.get("move") or "",
            san=data.get("san") or "",
            timestamp=data.get("timestamp") or "",
            type=data.get("type") or "human",
        )


@dataclass
class GameState:
    game_id: str
    start_time: str = field(default_factory=now_str)
    mode: str = ""  # ai | self
    player_color: str = ""  # white | black（人机模式下玩家所执颜色）
    ai_level: str = DEFAULT_AI_LEVEL
    moves: list[MoveRecord] = field(default_factory=list)
    result: str = "ongoing"
    end_time: str = ""
    version: int = 0
    board: chess.Board = field(default_factory=chess.Board)

    # --- 创建 / 水合 ---
    @classmethod
    def new(cls, mode: str = "", player_color: str = "", ai_level: str = DEFAULT_AI_LEVEL) -> "GameState":
        return cls(
            game_id=str(uuid.uuid4()),
            mode=mode or "",
            player_color=player_color or "",
            ai_level=ai_level or DEFAULT_AI_LEVEL,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        state = cls(
            game_id=data["game_id"],
            start_time=data.get("start_time") or now_str(),
            mode=data.get("mode") or "",
            player_color=data.get("player_color") or "",
            ai_level=data.get("ai_level") or DEFAULT_AI_LEVEL,
            result=data.get("result") or "ongoing",
            end_time=data.get("end_time") or "",
        )
        # 回放走法重建棋盘（非法走法跳过，保证旧数据也能载入）
        for raw in data.get("moves") or []:
            record = MoveRecord.from_dict(raw)
            try:
                move = state.board.parse_uci(record.move)
            except ValueError:
                continue
            if move not in state.board.legal_moves:
                continue
            state.board.push(move)
            state.moves.append(record)
        return state

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "mode": self.mode,
            "player_color": self.player_color,
            "ai_level": self.ai_level,
            "result": self.result,
            "moves": [record.to_dict() for record in self.moves],
        }

    # --- 变更 ---
    def touch(self) -> None:
        self.version += 1

    def refresh_result(self) -> str:
        self.result = evaluate_result(self.board)
        return self.result

    @property
    def finished(self) -> bool:
        return self.result not in ("ongoing", "")

    def last_move(self) -> Optional[dict]:
        if not self.board.move_stack:
            return None
        move = self.board.move_stack[-1]
        return {"from": chess.square_name(move.from_square), "to": chess.square_name(move.to_square), "uci": move.uci()}

    # --- 视图 ---
    def board_state(self) -> dict:
        board = self.board
        return {
            "fen": board.fen(),
            "legal_moves": [move.uci() for move in board.legal_moves],
            "is_check": board.is_check(),
            "is_checkmate": board.is_checkmate(),
            "is_stalemate": board.is_stalemate(),
            "is_game_over": board.is_game_over(claim_draw=False),
            "turn": "white" if board.turn else "black",
            "game_result": self.result,
            "last_move": self.last_move(),
            "fullmove_number": board.fullmove_number,
            "halfmove_clock": board.halfmove_clock,
        }

    def game_info(self) -> dict:
        return {
            "game_id": self.game_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "mode": self.mode,
            "player_color": self.player_color,
            "ai_level": self.ai_level,
            "result": self.result,
            "version": self.version,
            "finished": self.finished,
        }

    def move_history(self) -> list[dict]:
        return [record.to_dict() for record in self.moves]

    def statistics(self) -> dict:
        moves = self.moves
        return {
            "total_moves": len(moves),
            "white_moves": sum(1 for move in moves if move.color == "white"),
            "black_moves": sum(1 for move in moves if move.color == "black"),
            "ai_moves": sum(1 for move in moves if move.type == "ai"),
            "human_moves": sum(1 for move in moves if move.type == "human"),
        }

    def snapshot(self) -> dict:
        return {
            "board_state": self.board_state(),
            "game_info": self.game_info(),
            "move_history": self.move_history(),
            "statistics": self.statistics(),
        }

    def summary(self) -> dict:
        return {
            "game_id": self.game_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "mode": self.mode,
            "player_color": self.player_color,
            "ai_level": self.ai_level,
            "result": self.result,
            "total_moves": len(self.moves),
        }

    # --- 走法 ---
    def side_to_move(self) -> str:
        return "white" if self.board.turn else "black"

    def intends_ai_move(self) -> bool:
        """人机模式下，当前轮次是否应由 AI 落子。"""
        return self.mode == "ai" and bool(self.player_color) and self.side_to_move() != self.player_color
