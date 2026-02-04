import tornado.web
import tornado.ioloop
from config import SERVER_HOST, getEnvPort
import os

# 导入所有 Handler
from handlers.board_handlers import BoardStateHandler, GameStatusAggregateHandler
from handlers.game_handlers import (
    MakeMoveHandler, AIHandler, ResetHandler, 
    SetGameModeHandler, GetAllHistoryHandler, UndoMoveHandler
)
from handlers.analysis_handlers import GameAnalysisHandler
from handlers.game_analysis_pgn_handler import GameAnalysisPGNHandler
from handlers.websocket_handlers import GameWebSocketHandler
from handlers.react_build_handler import ReactHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# React 打包后的静态资源目录
REACT_STATIC_PATH = os.path.join(BASE_DIR, "static", "react_build", "static")

def make_app():
    return tornado.web.Application(
        [
            # API 路由
            (r"/api/board", BoardStateHandler),
            (r"/api/game_status", GameStatusAggregateHandler),
            (r"/api/move", MakeMoveHandler),
            (r"/api/ai", AIHandler),
            (r"/api/reset", ResetHandler),
            (r"/api/set_mode", SetGameModeHandler),
            (r"/api/get_all_history", GetAllHistoryHandler),
            (r"/api/undo", UndoMoveHandler),
            (r"/api/game_analysis", GameAnalysisHandler),
            (r"/ws/game", GameWebSocketHandler),
            (r"/api/analyse_pgn", GameAnalysisPGNHandler),

            # 静态资源路由（指向 React 打包目录）
            (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": REACT_STATIC_PATH}),

            # 所有其他路径返回 React index.html
            (r".*", ReactHandler),
        ],
        template_path=os.path.join(BASE_DIR, "templates"),
        static_path=os.path.join(BASE_DIR, "static"),
        debug=True
    )

if __name__ == "__main__":
    app = make_app()
    SERVER_PORT = getEnvPort()
    server = tornado.web.HTTPServer(app)
    server.bind(SERVER_PORT, address=SERVER_HOST)
    server.start()
    print(f"Tornado server running on http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"WebSocket server running on ws://{SERVER_HOST}:{SERVER_PORT}/ws/game")
    tornado.ioloop.IOLoop.current().start()