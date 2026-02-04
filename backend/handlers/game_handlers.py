import json
import uuid
from datetime import datetime
import chess
import chess.engine
from .base_handler import BaseHandler
from config import STOCKFISH_PATH, AI_CONFIG
from utils import (
    global_state, save_game_data, reset_current_game, 
    broadcast_game_update, get_game_result
)

class MakeMoveHandler(BaseHandler):
    """玩家走棋接口"""
    def post(self):
        try:
            data = json.loads(self.request.body)
            move_uci = data.get("move")
            
            board = global_state["board"]
            current_game = global_state["current_game"]
            
            move_number = len(current_game["moves"]) + 1
            color = "white" if board.turn else "black"
            move_info = {
                "move_number": move_number,
                "color": color,
                "move": move_uci,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": "human"
            }
            
            move = chess.Move.from_uci(move_uci)
            if move in board.legal_moves:
                board.push(move)
                current_game["moves"].append(move_info)
                current_game["result"] = get_game_result(board)
                save_game_data(current_game)
                
                # 广播更新
                broadcast_game_update()
                
                self.write(json.dumps({
                    "success": True,
                    "fen": board.fen(),
                    "move_info": move_info
                }))
            else:
                self.write(json.dumps({"success": False, "error": "Invalid move"}))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": str(e)}))

class AIHandler(BaseHandler):
    """AI走棋接口"""
    def post(self):
        try:
            data = json.loads(self.request.body)
            ai_level = data.get("ai_level", "normal")
            
            board = global_state["board"]
            current_game = global_state["current_game"]
            current_game["ai_level"] = ai_level
            
            # 获取AI配置
            ai_config = AI_CONFIG.get(ai_level, AI_CONFIG["normal"])
            
            # 执行AI走棋
            with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
                result = engine.play(
                    board, 
                    chess.engine.Limit(
                        time=ai_config["time_limit"], 
                        depth=ai_config["depth_limit"]
                    )
                )
                ai_move = str(result.move)
                board.push(result.move)
                
                # 记录AI走棋
                move_number = len(current_game["moves"]) + 1
                color = "white" if not board.turn else "black"
                move_info = {
                    "move_number": move_number,
                    "color": color,
                    "move": ai_move,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "ai"
                }
                current_game["moves"].append(move_info)
                current_game["result"] = get_game_result(board)
                save_game_data(current_game)
                
                # 广播更新
                broadcast_game_update()
                
                response = {
                    "success": True,
                    "ai_move": ai_move,
                    "fen": board.fen(),
                    "ai_level": ai_level,
                    "move_info": move_info
                }
                self.write(json.dumps(response))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": str(e)}))

class ResetHandler(BaseHandler):
    """重置游戏接口"""
    def post(self):
        reset_current_game()
        self.write(json.dumps({
            "success": True, 
            "fen": global_state["board"].fen(), 
            "new_game_id": global_state["current_game"]["game_id"]
        }))

class SetGameModeHandler(BaseHandler):
    """设置游戏模式接口"""
    def post(self):
        try:
            data = json.loads(self.request.body)
            mode = data.get("mode")
            player_color = data.get("player_color", "")
            
            current_game = global_state["current_game"]
            current_game["mode"] = mode
            current_game["player_color"] = player_color
            current_game["ai_level"] = data.get("ai_level", "normal")
            
            save_game_data(current_game)
            broadcast_game_update()
            
            self.write(json.dumps({
                "success": True,
                "game_id": current_game["game_id"],
                "mode": mode,
                "player_color": player_color
            }))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": str(e)}))

# handlers/game_handlers.py 中的 GetAllHistoryHandler 适配
import tornado.web
from utils import list_all_game_ids, load_single_game

class GetAllHistoryHandler(tornado.web.RequestHandler):
    """获取所有游戏历史（适配单局存储）"""
    def get(self):
        try:
            # 获取所有游戏ID
            game_ids = list_all_game_ids()
            # 可选：加载每局的简要信息（仅基础信息，不加载完整走法）
            history_summary = []
            for game_id in game_ids:
                game_data = load_single_game(game_id)
                if game_data:
                    # 仅返回简要信息，避免数据量过大
                    history_summary.append({
                        "game_id": game_id,
                        "start_time": game_data["start_time"],
                        "end_time": game_data["end_time"],
                        "mode": game_data["mode"],
                        "result": game_data["result"],
                        "total_moves": len(game_data["moves"])
                    })
            
            self.write({
                "success": True,
                "game_count": len(history_summary),
                "games": history_summary
            })
        except Exception as e:
            self.write({
                "success": False,
                "error": str(e)
            })

class UndoMoveHandler(BaseHandler):
    """悔棋接口"""
    def post(self):
        try:
            board = global_state["board"]
            current_game = global_state["current_game"]
            
            # 检查是否有走棋记录
            if len(current_game["moves"]) == 0:
                self.write(json.dumps({
                    'success': False,
                    'error': '暂无走棋记录，无法悔棋'
                }))
                return

            # 撤销棋盘最后一步
            if board.move_stack:
                board.pop()
            
            # 撤销走棋历史
            current_game["moves"].pop()
            
            # 更新游戏结果
            current_game["result"] = "ongoing"
            
            # 保存更新
            save_game_data(current_game)
            
            # 广播更新
            broadcast_game_update()
            
            # 生成响应
            legal_moves = [str(move) for move in board.legal_moves]
            result = get_game_result(board)
            
            self.write(json.dumps({
                'success': True,
                'fen': board.fen(),
                'turn': "white" if board.turn else "black",
                'legal_moves': legal_moves,
                'is_check': board.is_check(),
                'is_checkmate': board.is_checkmate(),
                'is_stalemate': board.is_stalemate(),
                'current_history': current_game["moves"],
                'game_result': result
            }))
        except Exception as e:
            self.write(json.dumps({
                'success': False,
                'error': str(e)
            }))