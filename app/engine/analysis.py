"""分析逻辑（纯引擎交互 + 白方视角归一化）。

所有评分统一换算为**白方视角**：``advantage_score > 0`` 表示白棋占优。
python-chess 的 ``PovScore.white()`` 直接给出白方视角分数，因此不再需要
过去那种「按 turn 手动翻转正负」的补丁（那是分数与标签互相矛盾的根因）。
"""

import io
import logging
from typing import Callable, Optional

import chess
import chess.engine
import chess.pgn

from app.config import (
    AI_LEVELS,
    ANALYSIS_CACHE_SIZE,
    BROADCAST_DEPTH,
    DEFAULT_AI_LEVEL,
    POSITION_DEPTH,
    POSITION_REPLY_DEPTH,
)
from app.engine.cache import LRUCache
from app.engine.pool import get_pool

logger = logging.getLogger(__name__)

_CACHE = LRUCache(ANALYSIS_CACHE_SIZE)


class AnalysisCancelled(Exception):
    """长棋谱分析任务被取消。"""


def configure_cache(maxsize: int) -> None:
    global _CACHE
    _CACHE = LRUCache(maxsize)


def cache_stats() -> dict:
    return _CACHE.stats()


# ---------------------------------------------------------------- 评分归一化


def _label_from_score(value: float) -> str:
    if value > 5:
        return "white_advantage"
    if value < -5:
        return "black_advantage"
    if value > 1:
        return "slight_white_advantage"
    if value < -1:
        return "slight_black_advantage"
    return "equal"


def _format_score_text(value: float, mate: Optional[int]) -> str:
    if mate is not None:
        if mate == 0:
            # 已经是将杀局面：由分值符号判断是哪一方造成的
            return "白方将杀" if value > 0 else "黑方将杀"
        return f"白方 {mate} 步将杀" if mate > 0 else f"黑方 {abs(mate)} 步将杀"
    if value > 0:
        return f"白优 +{value}"
    if value < 0:
        return f"黑优 {value}"
    return "均势"


def summarise_pov_score(pov_score: chess.engine.PovScore) -> tuple[float, Optional[int], str]:
    """把 PovScore 归一化为 (白方视角分值, 将杀步数, 优势标签)。"""
    score = pov_score.white()

    if score.is_mate():
        mate = score.mate()
        if mate is None:
            return 0.0, None, "unknown"
        if mate == 0:
            return (100.0, 0, "white_winning")
        if mate > 0:
            return 100.0, mate, "white_winning"
        return -100.0, mate, "black_winning"

    centipawns = score.score()
    if centipawns is None:
        return 0.0, None, "unknown"
    value = round(centipawns / 100.0, 2)
    return value, None, _label_from_score(value)


def terminal_evaluation(board: chess.Board) -> Optional[tuple[float, Optional[int], str]]:
    """终局局面无需搜索即可给出分数。非终局返回 None。"""
    if board.is_checkmate():
        # 行棋方被将死 → 对手获胜
        white_wins = not board.turn
        return (100.0, 0, "white_winning") if white_wins else (-100.0, 0, "black_winning")
    if (
        board.is_stalemate()
        or board.is_insufficient_material()
        or board.is_seventyfive_moves()
        or board.is_fivefold_repetition()
    ):
        return 0.0, None, "equal"
    return None


# ---------------------------------------------------------------- 局面分析


def _analyse_board(engine, board: chess.Board, depth: int, with_best_moves: bool) -> dict:
    terminal = terminal_evaluation(board)
    if terminal is not None:
        value, mate, label = terminal
        return {
            "success": True,
            "fen": board.fen(),
            "depth": depth,
            "advantage": label,
            "advantage_score": value,
            "mate_in": mate,
            "score_text": _format_score_text(value, mate),
            "current_best_move": "",
            "white_best_move": "",
            "black_best_move": "",
            "terminal": True,
        }

    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    value, mate, label = summarise_pov_score(info["score"])

    result = {
        "success": True,
        "fen": board.fen(),
        "depth": depth,
        "advantage": label,
        "advantage_score": value,
        "mate_in": mate,
        "score_text": _format_score_text(value, mate),
        "current_best_move": "",
        "white_best_move": "",
        "black_best_move": "",
        "terminal": False,
    }
    if not with_best_moves:
        return result

    try:
        play = engine.play(board, chess.engine.Limit(depth=min(depth, POSITION_REPLY_DEPTH + 2)))
    except chess.engine.EngineError as exc:
        logger.warning("最佳走法搜索失败：%s", exc)
        return result

    if not play.move:
        return result

    best_uci = play.move.uci()
    result["current_best_move"] = best_uci
    side = "white" if board.turn else "black"
    result[f"{side}_best_move"] = best_uci

    # 对手最佳应手
    reply_board = board.copy()
    reply_board.push(play.move)
    if any(reply_board.legal_moves):
        try:
            reply = engine.play(
                reply_board, chess.engine.Limit(depth=POSITION_REPLY_DEPTH)
            )
            if reply.move:
                opponent = "black" if board.turn else "white"
                result[f"{opponent}_best_move"] = reply.move.uci()
        except chess.engine.EngineError as exc:
            logger.warning("对手最佳应手搜索失败：%s", exc)
    return result


async def analyse_position(
    fen: str, depth: Optional[int] = None, *, with_best_moves: bool = True
) -> dict:
    """局面分析（带缓存）。引擎不可用时抛 EngineUnavailable 由上层转成 HTTP 错误。"""
    depth = int(depth or POSITION_DEPTH)
    key = ("position", fen, depth, with_best_moves)
    cached = _CACHE.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    board = chess.Board(fen)

    def job(engine):
        return _analyse_board(engine, board, depth, with_best_moves)

    result = await get_pool().run(job)
    _CACHE.set(key, result)
    return {**result, "cached": False}


async def analyse_current(board: chess.Board, depth: Optional[int] = None) -> dict:
    """按棋盘对象分析（会走缓存，key 仍是 FEN）。"""
    return await analyse_position(board.fen(), depth or BROADCAST_DEPTH)


# ---------------------------------------------------------------- AI 走棋


async def choose_ai_move(fen: str, level: str = DEFAULT_AI_LEVEL) -> str:
    config = AI_LEVELS.get(level) or AI_LEVELS[DEFAULT_AI_LEVEL]
    board = chess.Board(fen)

    def job(engine):
        play = engine.play(
            board,
            chess.engine.Limit(time=config["time_limit"], depth=config["depth"]),
        )
        return play.move.uci() if play.move else ""

    move = await get_pool().run(job)
    if not move:
        raise RuntimeError("引擎没有给出可用走法")
    return move


# ---------------------------------------------------------------- 长棋谱分析


def _analyse_pgn_sync(
    engine,
    pgn_text: str,
    depth: int,
    on_progress: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> dict:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("PGN 解析失败：请检查格式是否为标准 PGN")

    moves = list(game.mainline_moves())
    if not moves:
        raise ValueError("PGN 中没有任何走法")

    total = len(moves)
    if total > 400:
        logger.warning("PGN 走法数较多（%s），分析可能耗时较久", total)
    if on_progress:
        on_progress(0, total)

    headers = game.headers
    game_info = {
        "event": headers.get("Event", "未知对局"),
        "date": headers.get("Date", ""),
        "white": headers.get("White", "白棋"),
        "black": headers.get("Black", "黑棋"),
        "result": headers.get("Result", "*"),
        "opening": headers.get("Opening", "未知开局"),
        "total_moves": total,
    }

    board = game.board()
    move_analysis: list[dict] = []
    key_moments: list[dict] = []
    prev_value: Optional[float] = None
    prev_mate: Optional[int] = None
    step_number = 1

    for index, move in enumerate(moves, start=1):
        if is_cancelled and is_cancelled():
            raise AnalysisCancelled()

        side = "white" if board.turn else "black"
        try:
            san = board.san(move)
        except (ValueError, AssertionError):
            san = move.uci()
        board.push(move)

        terminal = terminal_evaluation(board)
        if terminal is not None:
            value, mate, label = terminal
        else:
            try:
                info = engine.analyse(board, chess.engine.Limit(depth=depth))
                value, mate, label = summarise_pov_score(info["score"])
            except chess.engine.EngineError as exc:
                logger.warning("第 %s 着分析失败：%s", index, exc)
                value, mate, label = (prev_value or 0.0), None, "unknown"

        # 失误 / 妙手：以「落子方视角」的分数变化判断
        move_type = "normal"
        if prev_value is not None:
            mover_is_white = side == "white"
            mate_now = mate is not None
            mate_before = prev_mate is not None
            if mate_now or mate_before:
                # 将杀分数用 ±100 作为哨兵，直接做差会得到 105 这类无意义数值，
                # 因此只判断「进入/脱离杀棋」这一方向性变化；
                # 杀棋序列内部（前后都是杀棋态）不再重复记为关键节点。
                if mate_now and not mate_before:
                    mating_side_is_mover = (value > 0) == mover_is_white
                    move_type = "excellent" if mating_side_is_mover else "error"
                    desc = "形成将杀" if mating_side_is_mover else "漏算被将杀"
                elif mate_before and not mate_now:
                    escaped = (prev_value > 0) != mover_is_white
                    move_type = "excellent" if escaped else "error"
                    desc = "化解杀棋" if escaped else "错失杀棋"
                else:
                    desc = ""
                    move_type = "normal"

                if desc:
                    key_moments.append(
                        {
                            "step_number": step_number,
                            "move_number": index,
                            "side": side,
                            "move": move.uci(),
                            "san": san,
                            "type": move_type,
                            "score_diff": None,
                            "desc": f"{'白' if mover_is_white else '黑'}方{desc}",
                        }
                    )
            else:
                delta = (value - prev_value) if mover_is_white else (prev_value - value)
                if delta <= -1.5:
                    move_type = "error"
                    key_moments.append(
                        {
                            "step_number": step_number,
                            "move_number": index,
                            "side": side,
                            "move": move.uci(),
                            "san": san,
                            "type": "error",
                            "score_diff": round(abs(delta), 2),
                            "desc": f"{'白' if mover_is_white else '黑'}方失误，局势下滑 {round(abs(delta), 2)}",
                        }
                    )
                elif delta >= 1.5:
                    move_type = "excellent"
                    key_moments.append(
                        {
                            "step_number": step_number,
                            "move_number": index,
                            "side": side,
                            "move": move.uci(),
                            "san": san,
                            "type": "excellent",
                            "score_diff": round(abs(delta), 2),
                            "desc": f"{'白' if mover_is_white else '黑'}方妙手，局势上升 {round(abs(delta), 2)}",
                        }
                    )

        if board.is_checkmate():
            move_type = "checkmate"
            key_moments.append(
                {
                    "step_number": step_number,
                    "move_number": index,
                    "side": side,
                    "move": move.uci(),
                    "san": san,
                    "type": "checkmate",
                    "desc": f"{'白' if side == 'white' else '黑'}方将杀",
                }
            )

        move_analysis.append(
            {
                "step_number": step_number,
                "move_number": index,
                "side": side,
                "move_uci": move.uci(),
                "move_san": san,
                "score_value": value,
                "score_text": _format_score_text(value, mate),
                "advantage": label,
                "move_type": move_type,
            }
        )

        prev_value = value
        prev_mate = mate
        if index % 2 == 0:
            step_number += 1
        if on_progress:
            on_progress(index, total)

    return {"game_info": game_info, "move_analysis": move_analysis, "key_moments": key_moments}


async def analyse_pgn(
    pgn_text: str,
    depth: int,
    on_progress: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> dict:
    """整局逐着分析。通过引擎池在线程池中执行，可中途取消。"""

    def job(engine):
        return _analyse_pgn_sync(engine, pgn_text, depth, on_progress, is_cancelled)

    return await get_pool().run(job)
