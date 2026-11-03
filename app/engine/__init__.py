"""Stockfish 引擎层：常驻进程池 + 线程池卸载 + 分析缓存 + 异步长棋谱任务。

设计要点
--------
* 引擎进程**常驻**（不再是每个请求 popen_uci 起停一次），创建后统一配置 Hash/Threads。
* 所有 UCI 交互都是阻塞调用，一律通过 ``run_in_executor`` 丢到线程池，
  Tornado 的 IOLoop 永不被引擎搜索阻塞。
* 池内每个引擎实例同一时刻只服务一个任务（``queue.LifoQueue`` 独占租借）。
"""

from app.engine.analysis import (
    AnalysisCancelled,
    analyse_pgn,
    analyse_position,
    choose_ai_move,
)
from app.engine.cache import LRUCache
from app.engine.jobs import JobManager, get_job_manager, shutdown_job_manager
from app.engine.pool import EnginePool, EngineUnavailable, get_pool, shutdown_pool

__all__ = [
    "AnalysisCancelled",
    "EnginePool",
    "EngineUnavailable",
    "JobManager",
    "LRUCache",
    "analyse_pgn",
    "analyse_position",
    "choose_ai_move",
    "get_job_manager",
    "get_pool",
    "shutdown_job_manager",
    "shutdown_pool",
]
