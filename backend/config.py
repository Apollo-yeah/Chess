import os

# 配置 Stockfish 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCKFISH_PATH = os.path.join(BASE_DIR, "stockfish/stockfish-macos-m1-apple-silicon")

# 服务器配置
SERVER_HOST = '0.0.0.0'

# 端口配置
def getEnvPort():
    return "{}".format(8156)

# 游戏数据存储配置（关键：改为按局存储）
GAME_DATA_DIR = "./game_data/"  # 每局游戏独立文件的存储目录
PGN_SAVE_DIR = "./game_pgn/"    # PGN文件存储目录（新增）

# 确保目录存在
os.makedirs(GAME_DATA_DIR, exist_ok=True)
os.makedirs(PGN_SAVE_DIR, exist_ok=True)

# AI 配置
AI_CONFIG = {
    "normal": {"time_limit": 1.0, "depth_limit": 5},
    "advanced": {"time_limit": 5.0, "depth_limit": 15}
}