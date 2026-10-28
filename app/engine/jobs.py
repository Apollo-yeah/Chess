"""长棋谱分析任务管理器。

一条 PGN 分析可能持续数十秒到数分钟，绝不能挂在一个 HTTP 请求上：
这里把它变成后台任务 —— 提交后立刻返回 ``job_id``，前端轮询进度，
支持取消，完成后保留一段时间供查询。
"""

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.config import ANALYSIS_JOBS_MAX, JOB_RETENTION_SECONDS, PGN_ANALYSIS_DEPTH
from app.engine.analysis import AnalysisCancelled, analyse_pgn
from app.engine.pool import EngineUnavailable

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"done", "error", "cancelled"}


@dataclass
class AnalysisJob:
    id: str
    depth: int
    pgn_text: str = ""
    status: str = "queued"  # queued | running | done | error | cancelled
    total: int = 0
    done: int = 0
    result: Optional[dict] = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)

    @property
    def finished(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def snapshot(self) -> dict:
        percent = round(self.done * 100.0 / self.total, 1) if self.total else 0.0
        payload = {
            "job_id": self.id,
            "status": self.status,
            "depth": self.depth,
            "progress": {
                "done": self.done,
                "total": self.total,
                "percent": percent,
            },
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }
        if self.status == "done" and self.result is not None:
            payload["result"] = self.result
        if self.finished_at:
            payload["elapsed"] = round(self.finished_at - (self.started_at or self.created_at), 2)
        return payload


class JobManager:
    def __init__(self, max_concurrent: int = ANALYSIS_JOBS_MAX, retention: int = JOB_RETENTION_SECONDS):
        self._jobs: dict[str, AnalysisJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrent)))
        self._retention = max(60, int(retention))
        self._lock = asyncio.Lock()

    # --- 查询 ---
    def get(self, job_id: str) -> Optional[AnalysisJob]:
        return self._jobs.get(job_id)

    def list(self) -> list[dict]:
        return [
            job.snapshot()
            for job in sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
        ]

    def stats(self) -> dict:
        active = sum(1 for job in self._jobs.values() if not job.finished)
        return {"total": len(self._jobs), "active": active}

    # --- 提交 / 取消 ---
    async def submit(self, pgn_text: str, depth: Optional[int] = None) -> AnalysisJob:
        job = AnalysisJob(
            id=uuid.uuid4().hex,
            depth=int(depth or PGN_ANALYSIS_DEPTH),
            pgn_text=pgn_text,
        )
        async with self._lock:
            self._prune_locked()
            self._jobs[job.id] = job
        self._tasks[job.id] = asyncio.create_task(self._run(job))
        return job

    def cancel(self, job_id: str) -> Optional[AnalysisJob]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if not job.finished:
            job.cancel_event.set()
            task = self._tasks.get(job_id)
            if task is not None and job.status == "queued":
                # 还没轮到执行，直接终结
                task.cancel()
        return job

    # --- 内部 ---
    def _progress(self, job: AnalysisJob, done: int, total: int) -> None:
        # 由引擎线程调用：仅做整数赋值，GIL 下即原子
        job.done = done
        job.total = total

    async def _run(self, job: AnalysisJob) -> None:
        try:
            async with self._semaphore:
                if job.cancel_event.is_set():
                    self._finish(job, "cancelled")
                    return
                job.status = "running"
                job.started_at = time.time()
                try:
                    result = await analyse_pgn(
                        job.pgn_text,
                        job.depth,
                        on_progress=lambda done, total: self._progress(job, done, total),
                        is_cancelled=job.cancel_event.is_set,
                    )
                except AnalysisCancelled:
                    self._finish(job, "cancelled")
                except (EngineUnavailable, ValueError) as exc:
                    self._finish(job, "error", str(exc))
                except Exception as exc:  # noqa: BLE001 - 任务失败不能拖垮服务
                    logger.exception("棋谱分析任务失败：%s", job.id)
                    self._finish(job, "error", str(exc))
                else:
                    job.result = result
                    job.done = job.total or job.done
                    self._finish(job, "done")
        except asyncio.CancelledError:
            self._finish(job, "cancelled")
        finally:
            job.pgn_text = ""  # 及时释放内存
            self._tasks.pop(job.id, None)

    def _finish(self, job: AnalysisJob, status: str, error: str = "") -> None:
        job.status = status
        job.error = error or job.error
        job.finished_at = time.time()
        logger.info("棋谱分析任务 %s 结束：%s", job.id, status)

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished and job.finished_at and now - job.finished_at > self._retention
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)

    async def shutdown(self) -> None:
        for job in self._jobs.values():
            if not job.finished:
                job.cancel_event.set()
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._jobs.clear()
        self._tasks.clear()


_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


async def shutdown_job_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.shutdown()
        _manager = None
