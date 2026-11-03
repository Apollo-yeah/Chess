"""集中配置：全部通过环境变量覆盖，本地开发与容器使用同一份代码路径。"""

import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    raw = raw.strip()
    return raw or default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_stockfish_path() -> str:
    """按优先级定位引擎：显式环境变量 → PATH → 仓库内自带的本地二进制。"""
    explicit = _env_str("STOCKFISH_PATH", "")
    if explicit:
        return explicit

    found = shutil.which("stockfish")
    if found:
        return found

    bundled = BASE_DIR / "stockfish"
    if bundled.is_dir():
        for candidate in sorted(bundled.iterdir()):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return ""


STOCKFISH_PATH = resolve_stockfish_path()

# --- 服务 ---
SERVER_HOST = _env_str("SERVER_HOST", "0.0.0.0")
DEBUG = _env_bool("CHESS_DEBUG", False)
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in _env_str("CHESS_CORS_ORIGINS", "").split(",")
    if origin.strip()
)


def get_env_port() -> str:
    return _env_str("PORT", "8156")


# --- 存储 ---
GAME_DATA_DIR = Path(_env_str("CHESS_DATA_DIR", str(BASE_DIR / "game_data")))
PGN_SAVE_DIR = Path(_env_str("CHESS_PGN_DIR", str(BASE_DIR / "game_pgn")))


def ensure_dirs() -> None:
    GAME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PGN_SAVE_DIR.mkdir(parents=True, exist_ok=True)

# --- 引擎池 ---
ENGINE_POOL_SIZE = _env_int("ENGINE_POOL_SIZE", 2)
ENGINE_HASH_MB = _env_int("ENGINE_HASH_MB", 64)
ENGINE_THREADS = _env_int("ENGINE_THREADS", 1)
ENGINE_START_TIMEOUT = _env_int("ENGINE_START_TIMEOUT", 20)

# --- 分析 ---
ANALYSIS_CACHE_SIZE = _env_int("ANALYSIS_CACHE_SIZE", 512)
POSITION_DEPTH = _env_int("ANALYSIS_DEPTH", 14)
POSITION_REPLY_DEPTH = _env_int("ANALYSIS_REPLY_DEPTH", 8)
BROADCAST_DEPTH = _env_int("BROADCAST_ANALYSIS_DEPTH", 12)
PGN_ANALYSIS_DEPTH = _env_int("PGN_ANALYSIS_DEPTH", 12)

# --- 长棋谱分析任务 ---
ANALYSIS_JOBS_MAX = _env_int("ANALYSIS_JOBS_MAX", 2)
JOB_RETENTION_SECONDS = _env_int("ANALYSIS_JOB_RETENTION", 3600)
MAX_PGN_BYTES = _env_int("ANALYSIS_MAX_PGN_BYTES", 1024 * 1024)
MAX_PGN_PLIES = _env_int("ANALYSIS_MAX_PGN_PLIES", 400)

# --- AI 对局等级 ---
AI_LEVELS = {
    "normal": {"time_limit": 1.0, "depth": 5},
    "advanced": {"time_limit": 5.0, "depth": 15},
}
DEFAULT_AI_LEVEL = "normal"

# --- 多对局注册表 ---
MAX_CACHED_GAMES = _env_int("MAX_CACHED_GAMES", 200)
