import os
import tornado.web
import tornado.ioloop

from app.config import SERVER_HOST, getEnvPort, STATIC_DIST_DIR
from app.handlers.board_handlers import BoardStateHandler, GameStatusAggregateHandler
from app.handlers.game_handlers import (
    MakeMoveHandler,
    AIHandler,
    ResetHandler,
    SetGameModeHandler,
    GetAllHistoryHandler,
    UndoMoveHandler,
)
from app.handlers.analysis_handlers import GameAnalysisHandler
from app.handlers.game_analysis_pgn_handler import GameAnalysisPGNHandler
from app.handlers.websocket_handlers import GameWebSocketHandler
from app.handlers.spa_handler import SpaHandler

ASSETS_DIR = os.path.join(STATIC_DIST_DIR, "assets")


def make_app():
    routes = [
        # API
        (r"/api/board", BoardStateHandler),
        (r"/api/game_status", GameStatusAggregateHandler),
        (r"/api/move", MakeMoveHandler),
        (r"/api/ai", AIHandler),
        (r"/api/reset", ResetHandler),
        (r"/api/set_mode", SetGameModeHandler),
        (r"/api/get_all_history", GetAllHistoryHandler),
        (r"/api/undo", UndoMoveHandler),
        (r"/api/game_analysis", GameAnalysisHandler),
        (r"/api/analyse_pgn", GameAnalysisPGNHandler),
        # WebSocket
        (r"/ws/game", GameWebSocketHandler),
    ]

    if os.path.isdir(ASSETS_DIR):
        routes.append(
            (r"/assets/(.*)", tornado.web.StaticFileHandler, {"path": ASSETS_DIR})
        )

    if os.path.isdir(STATIC_DIST_DIR):
        routes.append(
            (
                r"/(favicon-v2\.svg|vite\.svg)",
                tornado.web.StaticFileHandler,
                {"path": STATIC_DIST_DIR},
            )
        )

    routes.append((r".*", SpaHandler))

    return tornado.web.Application(routes, debug=True)


def main():
    app = make_app()
    port = getEnvPort()
    server = tornado.web.HTTPServer(app)
    server.bind(int(port), address=SERVER_HOST)
    server.start()
    print(f"Tornado server running on http://{SERVER_HOST}:{port}")
    print(f"WebSocket server running on ws://{SERVER_HOST}:{port}/ws/game")
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
