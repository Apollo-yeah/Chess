# 基础 Handler，处理跨域
import tornado.web

class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        """设置跨域头部"""
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def options(self):
        """处理OPTIONS预检请求"""
        self.set_status(204)
        self.finish()