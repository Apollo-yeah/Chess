import os
import tornado.web
from app.config import STATIC_DIST_DIR


class SpaHandler(tornado.web.RequestHandler):
    """SPA 回退：所有非 API / 静态资源路径返回 index.html"""

    def get(self):
        index_path = os.path.join(STATIC_DIST_DIR, "index.html")
        if not os.path.isfile(index_path):
            self.set_status(503)
            self.write(
                "<h1>Frontend not built</h1>"
                "<p>Run <code>npm run build</code> or <code>npm run dev</code> first.</p>"
            )
            return
        self.set_header("Content-Type", "text/html; charset=utf-8")
        with open(index_path, "r", encoding="utf-8") as f:
            self.write(f.read())
