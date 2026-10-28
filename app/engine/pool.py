"""Stockfish 常驻进程池。

* ``run()`` 是唯一的对外入口：把一个「拿到引擎后要做什么」的同步函数丢进线程池执行。
* 引擎实例通过有界队列独占租借，池大小固定，避免进程数失控。
* 引擎异常（崩溃 / 管道断开）时销毁实例，下次需要时重建，不会污染池。
"""

import logging
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import chess.engine
from tornado.ioloop import IOLoop

from app.config import (
    ENGINE_HASH_MB,
    ENGINE_POOL_SIZE,
    ENGINE_START_TIMEOUT,
    ENGINE_THREADS,
    STOCKFISH_PATH,
)

logger = logging.getLogger(__name__)

# 引擎崩溃类异常：出现这些就丢弃该实例
_FATAL_ENGINE_ERRORS = (
    chess.engine.EngineError,
    chess.engine.EngineTerminatedError,
    BrokenPipeError,
    ConnectionResetError,
    OSError,
)


class EngineUnavailable(RuntimeError):
    """引擎不可用（未安装 / 路径错误 / 启动失败）。"""


class EnginePool:
    def __init__(
        self,
        path: str,
        size: int = ENGINE_POOL_SIZE,
        hash_mb: int = ENGINE_HASH_MB,
        threads: int = ENGINE_THREADS,
    ):
        self.path = path or ""
        self.size = max(1, int(size))
        self.hash_mb = max(1, int(hash_mb))
        self.threads = max(1, int(threads))

        self._idle: "queue.LifoQueue[chess.engine.SimpleEngine]" = queue.LifoQueue()
        self._created = 0
        self._created_lock = threading.Lock()
        self._closed = False

        # 租借不到的等待上限，防止线程池被永久占满
        self._borrow_timeout = max(30.0, float(ENGINE_START_TIMEOUT) * 3)
        # 只有引擎在跑搜索任务的线程，池大小 + 2 足够
        self._executor = ThreadPoolExecutor(
            max_workers=self.size + 2, thread_name_prefix="stockfish"
        )

    # --- 状态 ---
    @property
    def available(self) -> bool:
        return bool(self.path) and os.path.isfile(self.path) and os.access(self.path, os.X_OK)

    def stats(self) -> dict:
        return {
            "path": self.path,
            "available": self.available,
            "pool_size": self.size,
            "instances": self._created,
            "idle": self._idle.qsize(),
            "hash_mb": self.hash_mb,
            "threads": self.threads,
        }

    def unavailable_reason(self) -> str:
        if not self.path:
            return (
                "未找到 Stockfish 可执行文件：请设置 STOCKFISH_PATH 环境变量，"
                "或把二进制放到 app/stockfish/ 目录下"
            )
        if not os.path.exists(self.path):
            return f"STOCKFISH_PATH 指向的文件不存在：{self.path}"
        return f"STOCKFISH_PATH 不可执行：{self.path}"

    # --- 实例生命周期 ---
    def _spawn(self) -> chess.engine.SimpleEngine:
        logger.info("启动 Stockfish 实例：%s", self.path)
        engine = chess.engine.SimpleEngine.popen_uci(
            self.path, timeout=float(ENGINE_START_TIMEOUT)
        )
        try:
            engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
        except chess.engine.EngineError as exc:  # 老版本引擎可能不支持某项
            logger.warning("引擎选项配置失败（忽略）：%s", exc)
        return engine

    def _acquire(self) -> chess.engine.SimpleEngine:
        try:
            return self._idle.get_nowait()
        except queue.Empty:
            pass

        with self._created_lock:
            can_create = self._created < self.size
            if can_create:
                self._created += 1

        if can_create:
            try:
                return self._spawn()
            except Exception:
                with self._created_lock:
                    self._created -= 1
                raise

        # 所有实例都在忙：等待归还
        try:
            return self._idle.get(timeout=self._borrow_timeout)
        except queue.Empty as exc:
            raise EngineUnavailable("引擎池繁忙，等待空闲引擎超时") from exc

    def _release(self, engine: chess.engine.SimpleEngine) -> None:
        if not self._closed:
            self._idle.put(engine)
            return
        self._destroy(engine)

    def _destroy(self, engine: chess.engine.SimpleEngine) -> None:
        with self._created_lock:
            self._created = max(0, self._created - 1)
        try:
            engine.quit()
        except Exception:
            pass

    def _run_sync(self, job: Callable[[chess.engine.SimpleEngine], object]):
        engine = self._acquire()
        fatal = False
        try:
            return job(engine)
        except _FATAL_ENGINE_ERRORS:
            fatal = True
            raise
        finally:
            if fatal:
                logger.warning("引擎实例异常，已丢弃并将在下次请求时重建")
                self._destroy(engine)
            else:
                self._release(engine)

    # --- 对外入口 ---
    async def run(self, job: Callable[[chess.engine.SimpleEngine], object]):
        """在线程池中执行 ``job(engine)``，返回其结果。IOLoop 不会被阻塞。"""
        if self._closed:
            raise EngineUnavailable("引擎池已关闭")
        if not self.available:
            raise EngineUnavailable(self.unavailable_reason())
        loop = IOLoop.current()
        return await loop.run_in_executor(self._executor, self._run_sync, job)

    async def close(self) -> None:
        self._closed = True
        engines = []
        while True:
            try:
                engines.append(self._idle.get_nowait())
            except queue.Empty:
                break
        for engine in engines:
            try:
                engine.quit()
            except Exception:
                pass
        with self._created_lock:
            self._created = 0
        self._executor.shutdown(wait=False)
        logger.info("引擎池已关闭")


_pool: Optional[EnginePool] = None
_pool_lock = threading.Lock()


def get_pool() -> EnginePool:
    """进程级单例引擎池（惰性创建）。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = EnginePool(STOCKFISH_PATH)
    return _pool


async def shutdown_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
