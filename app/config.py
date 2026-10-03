import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Stockfish 引擎路径
STOCKFISH_PATH = os.path.join(BASE_DIR, "stockfish", "stockfish-macos-m1-apple-silicon")

# 服务器配置
SERVER_HOST = "0.0.0.0"


def getEnvPort():
    return os.environ.get("PORT", "8156")


# 游戏数据存储（相对于 app/ 目录）
GAME_DATA_DIR = os.path.join(BASE_DIR, "game_data")
PGN_SAVE_DIR = os.path.join(BASE_DIR, "game_pgn")

os.makedirs(GAME_DATA_DIR, exist_ok=True)
os.makedirs(PGN_SAVE_DIR, exist_ok=True)

# AI 配置
AI_CONFIG = {
    "normal": {"time_limit": 1.0, "depth_limit": 5},
    "advanced": {"time_limit": 5.0, "depth_limit": 15},
}

# 前端构建产物目录
STATIC_DIST_DIR = os.path.join(BASE_DIR, "static", "dist")
