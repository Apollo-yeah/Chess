import json
import chess
import chess.engine
from .base_handler import BaseHandler
from config import STOCKFISH_PATH
from utils import global_state

class GameAnalysisHandler(BaseHandler):
    """棋局分析接口"""
    def get(self):
        try:
            # 初始化返回结果，默认值更安全
            analysis_result = {
                "success": False,
                "advantage": "unknown",
                "advantage_score": 0,
                "white_best_move": "",
                "black_best_move": "",
                "current_best_move": "",
                "error": ""
            }
            
            # 获取全局棋盘，增加空值判断
            board = global_state.get("board")
            if board is None:
                analysis_result["error"] = "全局棋盘未初始化"
                self.write(json.dumps(analysis_result))
                return
            
            # 检查棋盘是否有合法走法
            if not any(board.legal_moves):
                analysis_result["error"] = "当前局面无合法走法（可能是将死/和棋）"
                self.write(json.dumps(analysis_result))
                return
            
            # 使用Stockfish进行分析
            try:
                with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
                    # 获取当前局面评分
                    info = engine.analyse(board, chess.engine.Limit(depth=15))
                    score = info["score"].relative
                    
                    # 计算优势分数
                    if score.is_mate():
                        mate_in = score.mate()
                        analysis_result["advantage_score"] = 100 if mate_in > 0 else -100
                        analysis_result["advantage"] = "white_winning" if mate_in > 0 else "black_winning"
                    else:
                        centipawn = score.score() or 0
                        normalized_score = centipawn / 100
                        analysis_result["advantage_score"] = round(normalized_score, 1)
                        
                        # 判断优势方
                        if normalized_score > 5:
                            analysis_result["advantage"] = "white_advantage"
                        elif normalized_score < -5:
                            analysis_result["advantage"] = "black_advantage"
                        elif normalized_score > 1:
                            analysis_result["advantage"] = "slight_white_advantage"
                        elif normalized_score < -1:
                            analysis_result["advantage"] = "slight_black_advantage"
                        else:
                            analysis_result["advantage"] = "equal"
                    
                    # ========= 核心修复：增加None判断 =========
                    # 获取当前回合最佳走法（增加异常捕获）
                    current_best_move = None
                    try:
                        current_best_move = engine.play(board, chess.engine.Limit(depth=10))
                    except chess.engine.EngineError as e:
                        analysis_result["error"] = f"获取最佳走法失败：{str(e)}"
                        self.write(json.dumps(analysis_result))
                        return
                    
                    # 检查是否获取到有效走法
                    if current_best_move and current_best_move.move:
                        analysis_result["current_best_move"] = str(current_best_move.move)
                        
                        # 计算双方最佳走法（增加None判断）
                        if board.turn:  # 白棋回合
                            analysis_result["white_best_move"] = str(current_best_move.move)
                            # 模拟白棋走最佳步，计算黑棋应对
                            temp_board = board.copy()
                            temp_board.push(current_best_move.move)
                            # 检查临时棋盘是否有合法走法
                            if any(temp_board.legal_moves):
                                black_response = engine.play(temp_board, chess.engine.Limit(depth=8))
                                if black_response and black_response.move:
                                    analysis_result["black_best_move"] = str(black_response.move)
                        else:  # 黑棋回合
                            analysis_result["black_best_move"] = str(current_best_move.move)
                            # 模拟黑棋走最佳步，计算白棋应对
                            temp_board = board.copy()
                            temp_board.push(current_best_move.move)
                            # 检查临时棋盘是否有合法走法
                            if any(temp_board.legal_moves):
                                white_response = engine.play(temp_board, chess.engine.Limit(depth=8))
                                if white_response and white_response.move:
                                    analysis_result["white_best_move"] = str(white_response.move)
                    else:
                        analysis_result["error"] = "当前局面无最佳走法（可能已结束）"
                        self.write(json.dumps(analysis_result))
                        return
                    
                    analysis_result["success"] = True
                    
            except Exception as e:
                analysis_result["error"] = f"分析失败：{str(e)}"
            
            self.write(json.dumps(analysis_result))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": f"接口异常：{str(e)}"}))