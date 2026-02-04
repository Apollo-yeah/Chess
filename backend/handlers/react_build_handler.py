import tornado
import os

class ReactHandler(tornado.web.RequestHandler):
    def get(self):
        # 获取项目根目录
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        index_path = os.path.join(root_dir, "static", "react_build", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            self.write(f.read())