"""GET /api/status — 主机、Nginx 与本服务的运行参数及稳定性判定。"""

import asyncio

from app.handlers.base_handler import BaseHandler
from app.status.collector import collect_status


class StatusHandler(BaseHandler):
    """采样在线程里完成，避免 CPU 采样的短暂等待卡住事件循环。"""

    async def get(self) -> None:
        payload = await asyncio.get_running_loop().run_in_executor(None, collect_status)
        self.write_json(payload)
