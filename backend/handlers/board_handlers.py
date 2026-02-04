# 棋盘状态相关接口
import json
from .base_handler import BaseHandler
from utils import global_state, get_game_result

class BoardStateHandler(BaseHandler):
    """获取棋盘当前状态"""
    def get(self):
        board = global_state["board"]
        current_game = global_state["current_game"]
        
        legal_moves = [str(move) for move in board.legal_moves]
        result = get_game_result(board)
        current_game["result"] = result
        
        response = {
            "fen": board.fen(),
            "legal_moves": legal_moves,
            "is_check": board.is_check(),
            "is_checkmate": board.is_checkmate(),
            "is_stalemate": board.is_stalemate(),
            "turn": "white" if board.turn else "black",
            "current_history": current_game["moves"],
            "game_result": result
        }
        self.write(json.dumps(response))

class GameStatusAggregateHandler(BaseHandler):
    """获取聚合的游戏状态"""
    def get(self):
        try:
            board = global_state["board"]
            current_game = global_state["current_game"]
            
            legal_moves = [str(move) for move in board.legal_moves]
            result = get_game_result(board)
            current_game["result"] = result
            
            from utils import get_game_statistics
            statistics = get_game_statistics(current_game["moves"])
            
            response = {
                "board_state": {
                    "fen": board.fen(),
                    "legal_moves": legal_moves,
                    "is_check": board.is_check(),
                    "is_checkmate": board.is_checkmate(),
                    "is_stalemate": board.is_stalemate(),
                    "turn": "white" if board.turn else "black",
                    "game_result": result
                },
                "game_info": {
                    "game_id": current_game["game_id"],
                    "start_time": current_game["start_time"],
                    "mode": current_game["mode"],
                    "player_color": current_game["player_color"],
                    "ai_level": current_game["ai_level"],
                    "result": current_game["result"],
                    "end_time": current_game["end_time"]
                },
                "move_history": current_game["moves"],
                "statistics": statistics
            }
            self.write(json.dumps(response))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": str(e)}))