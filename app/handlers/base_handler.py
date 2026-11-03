"""Handler 基类：统一 JSON 响应、JSON 错误、按需 CORS。"""

import json
import logging
from typing import Any

import tornado.web

from app.config import CORS_ORIGINS
from app.game.service import GameError

logger = logging.getLogger(__name__)


class BaseHandler(tornado.web.RequestHandler):
    """所有 API handler 的基类。

    CORS 默认**关闭**（前后端同源部署，由 Nginx 反代，本就不需要跨域）；
    仅当显式配置 ``CHESS_CORS_ORIGINS`` 时才回显允许的来源。
    """

    def set_default_headers(self) -> None:
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Cache-Control", "no-store")
        self.set_header("X-Content-Type-Options", "nosniff")
        self._apply_cors()

    def _apply_cors(self) -> None:
        origin = self.request.headers.get("Origin")
        if not origin or not CORS_ORIGINS:
            return
        if origin in CORS_ORIGINS or "*" in CORS_ORIGINS:
            self.set_header("Access-Control-Allow-Origin", origin)
            self.set_header("Vary", "Origin")
            self.set_header(
                "Access-Control-Allow-Headers", "Content-Type, Authorization"
            )
            self.set_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")

    def options(self, *args: Any, **kwargs: Any) -> None:
        self.set_status(204)
        self.finish()

    # --- 工具 ---
    def write_json(self, payload: dict, status: int = 200) -> None:
        self.set_status(status)
        self.write(json.dumps(payload, ensure_ascii=False))

    def read_json_body(self) -> dict:
        if not self.request.body:
            return {}
        try:
            data = json.loads(self.request.body)
        except json.JSONDecodeError as exc:
            raise GameError("请求体必须是合法 JSON") from exc
        if not isinstance(data, dict):
            raise GameError("请求体必须是 JSON 对象")
        return data

    def write_error(self, status_code: int, **kwargs: Any) -> None:
        """Tornado 默认返回 HTML 错误页，这里统一成 JSON。"""
        message = "服务器内部错误"
        if status_code == 404:
            message = "接口不存在"
        elif status_code == 405:
            message = "请求方法不被支持"
        elif status_code == 500:
            exc_info = kwargs.get("exc_info")
            if exc_info is not None:
                message = str(exc_info[1])
                logger.error("请求处理失败", exc_info=exc_info)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.finish(json.dumps({"success": False, "error": message}, ensure_ascii=False))

    def handle_game_error(self, exc: Exception) -> None:
        status = getattr(exc, "status", 400)
        self.write_json({"success": False, "error": str(exc)}, status=status)
