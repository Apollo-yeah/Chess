import json
import os
import uuid
from datetime import datetime
import chess
import chess.pgn

from config import GAME_DATA_DIR, PGN_SAVE_DIR
import tornado

# 全局状态管理
global_state = {
    "board": chess.Board(),
    "current_game": {
        "game_id": str(uuid.uuid4()),
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "",
        "player_color": "",
        "ai_level": "normal",
        "moves": [],
        "result": "ongoing",
        "end_time": ""
    }
}

# WebSocket 客户端连接池
websocket_clients = set()

def get_game_file_path(game_id):
    """获取单局游戏的JSON文件路径"""
    return os.path.join(GAME_DATA_DIR, f"{game_id}.json")

def load_single_game(game_id):
    """加载单局游戏数据"""
    game_path = get_game_file_path(game_id)
    if os.path.exists(game_path):
        try:
            with open(game_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"警告：游戏{game_id}的JSON文件解析失败")
            return None
    return None

def list_all_game_ids(filter_condition=None):
    """
    获取所有游戏ID（核心修复：完整实现+过滤+排序）
    :param filter_condition: 过滤函数（可选），如 lambda x: x["result"] == "white_win"
    :return: 按修改时间倒序的游戏ID列表
    """
    try:
        game_ids = []
        # 遍历存储目录，获取所有JSON文件
        if not os.path.exists(GAME_DATA_DIR):
            return []
        
        for filename in os.listdir(GAME_DATA_DIR):
            if filename.endswith(".json"):
                game_id = filename[:-5]  # 去掉.json后缀
                # 应用过滤条件
                if filter_condition:
                    game_data = load_single_game(game_id)
                    if game_data and filter_condition(game_data):
                        game_ids.append(game_id)
                else:
                    game_ids.append(game_id)
        
        # 按文件修改时间倒序（最新对局在前）
        def get_file_mtime(game_id):
            file_path = get_game_file_path(game_id)
            return os.path.getmtime(file_path) if os.path.exists(file_path) else 0
        
        game_ids.sort(key=get_file_mtime, reverse=True)
        return game_ids
    except Exception as e:
        print(f"获取游戏ID列表失败：{str(e)}")
        return []

def save_game_data(game_data):
    """保存单局游戏数据（核心：独立文件+对局结束自动生成PGN）"""
    try:
        game_path = get_game_file_path(game_data["game_id"])
        # 保存为独立JSON文件
        with open(game_path, 'w', encoding='utf-8') as f:
            json.dump(game_data, f, ensure_ascii=False, indent=2)
        
        # 对局结束时生成PGN
        if game_data["result"] != "ongoing":
            generate_pgn_from_game_data(game_data)
    except Exception as e:
        print(f"保存游戏数据失败：{str(e)}")

def generate_pgn_from_game_data(game_data):
    try:
        moves = game_data.get("moves", [])
        if not moves:
            print(f"警告：游戏{game_data['game_id']}无走法记录，跳过PGN生成")
            return
        
        move_types = [m.get("type") for m in moves]
        is_human_vs_human = all(t == "human" for t in move_types)
        is_human_vs_ai = "human" in move_types and "ai" in move_types
        is_ai_vs_ai = all(t == "ai" for t in move_types)

        white_player = "Human"
        black_player = "Human"
        if is_human_vs_ai:
            white_type = next(m.get("type") for m in moves if m.get("color") == "white")
            black_type = next(m.get("type") for m in moves if m.get("color") == "black")
            white_player = "Human" if white_type == "human" else f"AI ({game_data['ai_level']})"
            black_player = "Human" if black_type == "human" else f"AI ({game_data['ai_level']})"
        elif is_ai_vs_ai:
            white_player = f"AI ({game_data['ai_level']})"
            black_player = f"AI ({game_data['ai_level']})"

        game_mode = game_data.get("mode", "").strip()
        if not game_mode:
            if is_human_vs_human:
                game_mode = "human_vs_human"
            elif is_human_vs_ai:
                game_mode = "human_vs_ai"
            else:
                game_mode = "ai_vs_ai"

        end_time = game_data.get("end_time", "").strip()
        if not end_time:
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            game_data["end_time"] = end_time
            # 同步保存到JSON文件
            with open(get_game_file_path(game_data["game_id"]), 'w', encoding='utf-8') as f:
                json.dump(game_data, f, ensure_ascii=False, indent=2)

        game = chess.pgn.Game()
        game.headers.update({
            "Event": f"Chess Game ({game_mode} mode)",
            "Site": "Local Game",
            "Date": game_data["start_time"].split()[0].replace("-", "."),
            "Round": "1",
            "White": white_player,
            "Black": black_player,
            "Result": convert_result_to_pgn_format(game_data["result"]),
            "StartTime": game_data["start_time"],
            "EndTime": end_time,
            "AILevel": game_data.get("ai_level", "normal"),
            "GameID": game_data["game_id"]
        })

        board = chess.Board()
        node = game
        for move_info in moves:
            uci_move = move_info.get("move", "").strip()
            if not uci_move:
                continue
            try:
                move = board.parse_uci(uci_move)
                if move in board.legal_moves:
                    node = node.add_variation(move)
                    board.push(move)
            except ValueError as e:
                print(f"跳过无效走法 {uci_move}：{e}")
                continue

        pgn_path = os.path.join(PGN_SAVE_DIR, f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.pgn")
        with open(pgn_path, 'w', encoding='utf-8') as f:
            exporter = chess.pgn.FileExporter(f)
            game.accept(exporter)

        print(f"PGN文件生成成功：{pgn_path}")
    except Exception as e:
        print(f"生成PGN失败：{str(e)}")

def convert_result_to_pgn_format(result):
    """转换结果为PGN标准格式"""
    mapping = {
        "white_win": "1-0",
        "black_win": "0-1",
        "draw": "1/2-1/2",
        "abandoned": "*",
        "ongoing": "*"
    }
    return mapping.get(result, "*")

def reset_current_game():
    """重置当前游戏状态（核心修复：强制设置end_time）"""
    try:
        # 保存上一局数据
        if global_state["current_game"]["moves"]:
            global_state["current_game"]["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if global_state["current_game"]["result"] == "ongoing":
                global_state["current_game"]["result"] = "abandoned"
            save_game_data(global_state["current_game"])
        
        # 初始化新游戏
        global_state["board"] = chess.Board()
        global_state["current_game"] = {
            "game_id": str(uuid.uuid4()),
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "",
            "player_color": "",
            "ai_level": "normal",
            "moves": [],
            "result": "ongoing",
            "end_time": ""
        }
        
        # 广播重置事件
        broadcast_game_update()
    except Exception as e:
        print(f"重置游戏状态失败：{str(e)}")

def get_game_result(board):
    """判断当前棋局结果"""
    if board.is_checkmate():
        return "black_win" if board.turn else "white_win"
    elif board.is_stalemate() or board.is_insufficient_material():
        return "draw"
    return "ongoing"

def get_game_statistics(moves):
    """计算游戏统计数据"""
    return {
        "total_moves": len(moves),
        "white_moves": len([m for m in moves if m["color"] == "white"]),
        "black_moves": len([m for m in moves if m["color"] == "black"]),
        "ai_moves": len([m for m in moves if m["type"] == "ai"]),
        "human_moves": len([m for m in moves if m["type"] == "human"])
    }

def broadcast_game_update():
    """广播游戏状态更新（安全版）"""
    clients = list(websocket_clients)
    for client in clients:
        try:
            tornado.ioloop.IOLoop.current().add_callback(client.send_full_update)
        except Exception as e:
            print(f"广播到客户端失败: {e}")
            if client in websocket_clients:
                websocket_clients.remove(client)

# 初始化（确保目录存在）
os.makedirs(GAME_DATA_DIR, exist_ok=True)
os.makedirs(PGN_SAVE_DIR, exist_ok=True)
reset_current_game()