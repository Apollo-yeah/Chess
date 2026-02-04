import json
import datetime
import tornado.websocket
from utils import websocket_clients, global_state, get_game_result, get_game_statistics
import chess.engine
from config import STOCKFISH_PATH

class GameWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, WEBSOCKET")

    def open(self):
        """新客户端连接 - 增加异常捕获"""
        try:
            print(f"WebSocket 客户端已连接: {self.request.remote_ip}")
            websocket_clients.add(self)
            # 立即推送一次完整数据（异步执行，避免阻塞）
            tornado.ioloop.IOLoop.current().add_callback(self.send_full_update)
        except Exception as e:
            print(f"WebSocket连接初始化失败: {e}")
            self.close()

    def on_close(self):
        """客户端断开连接 - 安全移除"""
        print(f"WebSocket 客户端已断开: {self.request.remote_ip}")
        if self in websocket_clients:
            try:
                websocket_clients.remove(self)
            except:
                pass

    def on_message(self, message):
        """处理客户端消息 - 增加异常捕获"""
        try:
            data = json.loads(message)
            if data.get("action") == "refresh":
                self.send_full_update()
        except json.JSONDecodeError:
            print(f"WebSocket消息解析失败: 非JSON格式 - {message}")
        except Exception as e:
            print(f"处理WebSocket消息失败: {e}")

    def send_full_update(self):
        """发送完整数据 - 彻底修复序列化+异常处理"""
        try:
            board = global_state["board"]
            current_game = global_state["current_game"]
            
            # 1. 构建状态数据（确保所有数据可序列化）
            legal_moves = [str(move) for move in board.legal_moves]
            result = get_game_result(board)
            current_game["result"] = result
            
            status_data = {
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
                    "end_time": current_game["end_time"] or ""
                },
                "move_history": current_game["moves"],
                "statistics": get_game_statistics(current_game["moves"])
            }
            
            # 2. 构建分析数据（单独异常捕获，避免分析失败导致连接断开）
            analysis_data = {"success": False}
            try:
                with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
                    info = engine.analyse(board, chess.engine.Limit(depth=15))
                    score = info["score"].relative
                    
                    if score.is_mate():
                        mate_in = score.mate()
                        analysis_data["advantage_score"] = 100 if mate_in > 0 else -100
                        analysis_data["advantage"] = "white_winning" if mate_in > 0 else "black_winning"
                    else:
                        centipawn = score.score() or 0
                        normalized_score = centipawn / 100
                        analysis_data["advantage_score"] = round(normalized_score, 1)
                        
                        if normalized_score > 5:
                            analysis_data["advantage"] = "white_advantage"
                        elif normalized_score < -5:
                            analysis_data["advantage"] = "black_advantage"
                        elif normalized_score > 1:
                            analysis_data["advantage"] = "slight_white_advantage"
                        elif normalized_score < -1:
                            analysis_data["advantage"] = "slight_black_advantage"
                        else:
                            analysis_data["advantage"] = "equal"
                    
                    current_best_move = engine.play(board, chess.engine.Limit(depth=10))
                    analysis_data["current_best_move"] = str(current_best_move.move)
                    
                    if board.turn:
                        analysis_data["white_best_move"] = str(current_best_move.move)
                        temp_board = board.copy()
                        temp_board.push(current_best_move.move)
                        black_response = engine.play(temp_board, chess.engine.Limit(depth=8))
                        analysis_data["black_best_move"] = str(black_response.move)
                    else:
                        analysis_data["black_best_move"] = str(current_best_move.move)
                        temp_board = board.copy()
                        temp_board.push(current_best_move.move)
                        white_response = engine.play(temp_board, chess.engine.Limit(depth=8))
                        analysis_data["white_best_move"] = str(white_response.move)
                    
                    analysis_data["success"] = True

                    # 始终以白色方的优势作为基准点位输出
                    analysis_score_right = 1 if board.turn else -1
                    analysis_data["advantage_score"] *= analysis_score_right
            except Exception as e:
                analysis_data["error"] = f"分析失败：{str(e)}"
                analysis_data["success"] = False
            
            # 3. 组合数据（修复时间序列化问题）
            full_data = {
                "type": "full_update",
                "status": status_data,
                "analysis": analysis_data,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 修复：用字符串而非JSON对象
            }
            
            # 4. 安全发送（确保数据可序列化）
            try:
                self.write_message(json.dumps(full_data, ensure_ascii=False))
            except json.JSONDecodeError:
                print("WebSocket数据序列化失败")
                # 发送简化版数据
                self.write_message(json.dumps({
                    "type": "error",
                    "message": "数据序列化失败"
                }))
            except tornado.websocket.WebSocketClosedError:
                print("WebSocket连接已关闭，跳过发送")
                
        except Exception as e:
            print(f"发送WebSocket数据失败: {e}")
            try:
                self.write_message(json.dumps({
                    "type": "error",
                    "message": f"服务器错误：{str(e)}"
                }))
            except:
                pass