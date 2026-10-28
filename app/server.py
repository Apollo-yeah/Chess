"""Tornado 应用装配与启动入口。

本服务**只提供 API 与 WebSocket**：前端静态资源由 Nginx（生产）或 Vite dev server
（开发）托管，因此这里不再有 SPA 回退与静态文件路由。
"""

import asyncio
import logging
import signal

import tornado.httpserver
import tornado.web

from app.config import (
    ANALYSIS_CACHE_SIZE,
    DEBUG,
    SERVER_HOST,
    STOCKFISH_PATH,
    ensure_dirs,
    get_env_port,
)
from app.engine.analysis import configure_cache
from app.engine.jobs import shutdown_job_manager
from app.engine.pool import get_pool, shutdown_pool
from app.handlers.analysis_handlers import (
    AnalysisJobHandler,
    AnalysisJobsHandler,
    HealthHandler,
)
from app.handlers.game_handlers import (
    CurrentGameHandler,
    GameAiMoveHandler,
    GameAnalysisHandler,
    GameModeHandler,
    GameMoveHandler,
    GameResetHandler,
    GameStateHandler,
    GameUndoHandler,
    GamesHandler,
)
from app.handlers.websocket_handlers import GameWebSocketHandler

logger = logging.getLogger(__name__)

GAME_ID_PATTERN = r"(?P<game_id>[0-9a-zA-Z\-]{1,64})"

ROUTES = [
    # --- 系统 ---
    (r"/api/health", HealthHandler),
    # --- 对局 ---
    (r"/api/games", GamesHandler),
    # 必须写在 /api/games/{game_id} 之前，否则 "current" 会被当成 game_id
    (r"/api/games/current", CurrentGameHandler),
    (rf"/api/games/{GAME_ID_PATTERN}", GameStateHandler),
    (rf"/api/games/{GAME_ID_PATTERN}/move", GameMoveHandler),
    (rf"/api/games/{GAME_ID_PATTERN}/ai", GameAiMoveHandler),
    (rf"/api/games/{GAME_ID_PATTERN}/undo", GameUndoHandler),
    (rf"/api/games/{GAME_ID_PATTERN}/mode", GameModeHandler),
    (rf"/api/games/{GAME_ID_PATTERN}/reset", GameResetHandler),
    (rf"/api/games/{GAME_ID_PATTERN}/analysis", GameAnalysisHandler),
    # --- 长棋谱分析任务 ---
    (r"/api/analysis/jobs", AnalysisJobsHandler),
    (r"/api/analysis/jobs/(?P<job_id>[0-9a-f]{6,64})", AnalysisJobHandler),
    # --- 实时推送 ---
    (r"/ws/game", GameWebSocketHandler),
]


def make_app() -> tornado.web.Application:
    return tornado.web.Application(
        ROUTES,
        debug=DEBUG,
        compress_response=True,
        websocket_ping_interval=25,
        websocket_ping_timeout=60,
    )


async def _serve() -> None:
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    ensure_dirs()
    configure_cache(ANALYSIS_CACHE_SIZE)

    port = int(get_env_port())
    app = make_app()
    server = tornado.httpserver.HTTPServer(app)
    try:
        server.bind(port, address=SERVER_HOST)
    except OSError as exc:
        logger.error(
            "端口 %s 无法绑定（%s）。请先停止占用该端口的进程，或用 PORT=<其他端口> 启动。",
            port,
            exc,
        )
        raise SystemExit(1) from exc
    server.start()

    pool = get_pool()
    logger.info("API 服务已启动：http://%s:%s", SERVER_HOST, port)
    logger.info("WebSocket：ws://%s:%s/ws/game", SERVER_HOST, port)
    if pool.available:
        logger.info("Stockfish 就绪：%s（池大小 %s）", STOCKFISH_PATH, pool.size)
    else:
        logger.warning("Stockfish 不可用：%s", pool.unavailable_reason())

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass

    try:
        await stop.wait()
    finally:
        logger.info("正在关闭：停止分析任务与引擎进程…")
        server.stop()
        await shutdown_job_manager()
        await shutdown_pool()


def main() -> None:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
