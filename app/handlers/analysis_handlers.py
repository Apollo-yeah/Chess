"""长棋谱分析任务接口 + 系统状态接口。

长棋谱分析被拆成「提交任务 → 轮询进度」两段，HTTP 请求不再挂着引擎跑几分钟。
"""

import logging

from app.config import MAX_PGN_BYTES, MAX_PGN_PLIES
from app.engine.jobs import get_job_manager
from app.engine.pool import EngineUnavailable
from app.game.service import GameError
from app.handlers.base_handler import BaseHandler

logger = logging.getLogger(__name__)


class AnalysisJobsHandler(BaseHandler):
    """GET  /api/analysis/jobs — 任务列表
    POST /api/analysis/jobs — 提交整局 PGN 分析任务
    """

    async def get(self) -> None:
        manager = get_job_manager()
        self.write_json({"success": True, "jobs": manager.list(), "stats": manager.stats()})

    async def post(self) -> None:
        body = self.read_json_body()
        pgn_text = (body.get("pgn_text") or "").strip()
        if not pgn_text:
            raise GameError("PGN 文本不能为空")

        raw = pgn_text.encode("utf-8")
        if len(raw) > MAX_PGN_BYTES:
            raise GameError(f"PGN 过大（{len(raw)} 字节，上限 {MAX_PGN_BYTES} 字节）")

        depth = body.get("depth")
        try:
            depth = int(depth) if depth is not None else None
        except (TypeError, ValueError):
            raise GameError("depth 必须是整数") from None
        if depth is not None and not (4 <= depth <= 24):
            raise GameError("depth 需在 4~24 之间")

        if pgn_text.count(" ") + 1 > MAX_PGN_PLIES * 2:
            logger.info("PGN 长度提示：走法数可能超过上限 %s", MAX_PGN_PLIES)

        manager = get_job_manager()
        job = await manager.submit(pgn_text, depth)
        self.write_json({"success": True, **job.snapshot()}, status=202)


class AnalysisJobHandler(BaseHandler):
    """GET    /api/analysis/jobs/{job_id} — 查询进度 / 结果
    DELETE /api/analysis/jobs/{job_id} — 取消任务
    """

    async def get(self, job_id: str) -> None:
        manager = get_job_manager()
        job = manager.get(job_id)
        if job is None:
            self.write_json({"success": False, "error": f"任务不存在：{job_id}"}, status=404)
            return
        self.write_json({"success": True, **job.snapshot()})

    async def delete(self, job_id: str) -> None:
        manager = get_job_manager()
        job = manager.cancel(job_id)
        if job is None:
            self.write_json({"success": False, "error": f"任务不存在：{job_id}"}, status=404)
            return
        self.write_json({"success": True, **job.snapshot()})


class HealthHandler(BaseHandler):
    """GET /api/health — 供容器 healthcheck 与运维排查使用"""

    async def get(self) -> None:
        from app.engine.analysis import cache_stats
        from app.engine.pool import get_pool
        from app.game.registry import get_registry
        from app.game.storage import storage_info

        pool = get_pool()
        engine = pool.stats()
        try:
            from app.engine.analysis import analyse_position

            probe = await analyse_position(
                "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                depth=4,
                with_best_moves=False,
            )
            engine["probe_ok"] = bool(probe.get("success"))
        except EngineUnavailable as exc:
            engine["probe_ok"] = False
            engine["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - 健康检查不能抛异常
            engine["probe_ok"] = False
            engine["error"] = str(exc)

        jobs = get_job_manager().stats()
        self.write_json(
            {
                "success": True,
                "status": "ok" if engine.get("probe_ok") else "degraded",
                "engine": engine,
                "jobs": jobs,
                "games": get_registry().stats(),
                "analysis_cache": cache_stats(),
                "storage": storage_info(),
            }
        )
