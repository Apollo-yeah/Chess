import json
import chess
import chess.pgn
import chess.engine
import io
from datetime import datetime
from tornado.web import RequestHandler  # 替换为你的BaseHandler

from config import STOCKFISH_PATH

class GameAnalysisPGNHandler(RequestHandler):
    """修正后的PGN分析接口"""
    def set_default_headers(self):
        """跨域配置（必须加）"""
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_header("Access-Control-Allow-Methods", "POST,OPTIONS")

    def options(self):
        """处理OPTIONS预检请求"""
        self.set_status(204)
        self.finish()

    def post(self):
        try:
            result = {
                "success": False,
                "error": "",
                "game_info": {},
                "move_analysis": [],
                "key_moments": []
            }

            # 1. 解析请求参数
            try:
                data = json.loads(self.request.body)
            except:
                result["error"] = "请求体必须是合法JSON"
                self.write(json.dumps(result, ensure_ascii=False))
                return
            
            pgn_text = data.get("pgn_text", "").strip()
            if not pgn_text:
                result["error"] = "PGN文本不能为空"
                self.write(json.dumps(result, ensure_ascii=False))
                return

            # 2. 解析PGN（修复重复走法解析问题）
            pgn_io = io.StringIO(pgn_text)
            game = chess.pgn.read_game(pgn_io)
            if not game:
                result["error"] = "PGN格式错误，请检查（建议用标准PGN）"
                self.write(json.dumps(result, ensure_ascii=False))
                return

            # 3. 提取对局基本信息
            result["game_info"] = {
                "event": game.headers.get("Event", "未知对局"),
                "date": game.headers.get("Date", datetime.now().strftime("%Y.%m.%d")),
                "white": game.headers.get("White", "白棋"),
                "black": game.headers.get("Black", "黑棋"),
                "result": game.headers.get("Result", "未知结果"),
                "opening": game.headers.get("Opening", "未知开局"),
                "total_moves": len(list(game.mainline_moves()))
            }

            # 4. 初始化分析环境
            board = game.board()
            engine = None
            try:
                engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
            except Exception as e:
                result["error"] = f"Stockfish引擎启动失败：{str(e)}（检查路径是否正确）"
                self.write(json.dumps(result, ensure_ascii=False))
                return

            move_analysis = []
            key_moments = []
            prev_score = 0  # 上一步评分
            move_count = 0  # 总走法数（白+黑为1步）
            step_number = 1  # 显示的步数（如1. e4 e5）

            # 5. 逐步分析（核心修正：走棋后分析局面）
            for move in game.mainline_moves():
                move_count += 1
                # 记录走棋方和走法
                side = "white" if (move_count % 2 == 1) else "black"
                move_uci = move.uci()
                move_san = board.san(move)

                # 执行走棋
                board.push(move)

                # 分析走棋后的局面（修正：分析走棋后的状态）
                try:
                    info = engine.analyse(
                        board, 
                        chess.engine.Limit(depth=12),  # 降低深度提升速度
                        multipv=1  # 只返回最佳走法
                    )
                except:
                    # 局面无法分析（如将死）
                    score_value = -100 if side == "white" else 100
                    score_text = "将死"
                    advantage = "black_winning" if side == "white" else "white_winning"
                else:
                    score = info[0]["score"].relative

                    # 计算评分（修正评分逻辑）
                    if score.is_mate():
                        mate_in = score.mate()
                        score_value = 100 if mate_in > 0 else -100
                        score_text = f"将死（{mate_in}步）"
                        advantage = "white_winning" if mate_in > 0 else "black_winning"
                    else:
                        centipawn = score.score() or 0
                        score_value = round(centipawn / 100, 2)
                        # 优势判断
                        if score_value > 3:
                            advantage = "white_advantage"
                            score_text = f"白优 +{score_value}"
                        elif score_value < -3:
                            advantage = "black_advantage"
                            score_text = f"黑优 {score_value}"
                        elif score_value > 0.5:
                            advantage = "slight_white_advantage"
                            score_text = f"白小幅优 +{score_value}"
                        elif score_value < -0.5:
                            advantage = "slight_black_advantage"
                            score_text = f"黑小幅优 {score_value}"
                        else:
                            advantage = "equal"
                            score_text = f"均势 {score_value}"

                # 判断关键步（评分变化>1.5分为失误/妙手）
                move_type = "normal"
                score_diff = abs(score_value - prev_score)
                if score_diff > 1.5:
                    if (side == "white" and score_value < prev_score) or (side == "black" and score_value > prev_score):
                        move_type = "error"
                        key_moments.append({
                            "step_number": step_number,
                            "move_number": move_count,
                            "side": side,
                            "move": move_uci,
                            "type": "error",
                            "score_diff": score_diff,
                            "desc": f"{side}方失误，评分变化{score_diff:.2f}"
                        })
                    else:
                        move_type = "excellent"
                        key_moments.append({
                            "step_number": step_number,
                            "move_number": move_count,
                            "side": side,
                            "move": move_uci,
                            "type": "excellent",
                            "score_diff": score_diff,
                            "desc": f"{side}方妙手，评分变化{score_diff:.2f}"
                        })

                # 判断绝杀
                if board.is_checkmate():
                    move_type = "checkmate"
                    key_moments.append({
                        "step_number": step_number,
                        "move_number": move_count,
                        "side": side,
                        "move": move_uci,
                        "type": "checkmate",
                        "desc": f"{side}方绝杀！"
                    })

                # 保存当前步分析
                move_analysis.append({
                    "step_number": step_number,  # 显示步数（如1/2/3）
                    "move_number": move_count,   # 总走法数（1-76）
                    "side": side,
                    "move_uci": move_uci,
                    "move_san": move_san,
                    "score_value": score_value,
                    "score_text": score_text,
                    "advantage": advantage,
                    "move_type": move_type
                })

                # 更新步数和上一步评分
                if move_count % 2 == 0:
                    step_number += 1
                prev_score = score_value

            # 6. 关闭引擎
            engine.quit()

            # 7. 组装结果
            result["success"] = True
            result["move_analysis"] = move_analysis
            result["key_moments"] = key_moments

            self.write(json.dumps(result, ensure_ascii=False, indent=2))

        except Exception as e:
            self.write(json.dumps({
                "success": False,
                "error": f"服务器错误：{str(e)}"
            }, ensure_ascii=False))