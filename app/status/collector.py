"""采集主机、Nginx 与本服务的运行参数，并按固定阈值给出稳定性判定。

判定只使用下面这些阈值（页面上会原样展示）：

* 系统负载：1 分钟负载 / CPU 核数，< 0.7 稳定，≥ 1.2 不稳定
* CPU：< 70% 稳定，≥ 90% 不稳定
* 内存：< 75% 稳定，≥ 90% 不稳定
* 交换分区：< 10% 稳定，≥ 40% 不稳定；未启用视为稳定
* 磁盘：< 80% 稳定，≥ 92% 不稳定；剩余不足 512 MB 直接不稳定
* Nginx 活跃连接 / worker_connections：< 60% 稳定，≥ 85% 不稳定
* Nginx 本轮新增「接受但未处理」的连接：出现即不稳定
* 近 15 分钟访问日志 5xx：0 稳定，≥ 10 次或不低于 5% 不稳定
* 近 15 分钟错误日志：0 稳定，≥ 8 条不稳定
* 引擎可执行文件缺失、Nginx 本应在线却无响应：不稳定
* 引擎池占满或分析任务打满并发上限：留意
* API 进程内存：< 1 GB 稳定，≥ 2.5 GB 不稳定
* 打开文件数 / 软上限：< 70% 稳定，≥ 90% 不稳定

开发环境没有 Nginx 时，相关项记为「不适用」，不拉低总判定。
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import resource
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from app.config import (
    ANALYSIS_CACHE_SIZE,
    ANALYSIS_JOBS_MAX,
    BROADCAST_DEPTH,
    ENGINE_HASH_MB,
    ENGINE_POOL_SIZE,
    ENGINE_THREADS,
    GAME_DATA_DIR,
    PGN_ANALYSIS_DEPTH,
    POSITION_DEPTH,
    SERVER_HOST,
    get_env_port,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESS_STARTED = time.time()
LOG_WINDOW = timedelta(minutes=15)
LOG_TAIL_BYTES = 1024 * 1024

LOAD_OK = 0.70
LOAD_CRIT = 1.20
CPU_OK = 70.0
CPU_CRIT = 90.0
MEM_OK = 75.0
MEM_CRIT = 90.0
SWAP_OK = 10.0
SWAP_CRIT = 40.0
DISK_OK = 80.0
DISK_CRIT = 92.0
DISK_FREE_CRIT = 512 * 1024 * 1024
NGINX_CONN_OK = 0.60
NGINX_CONN_CRIT = 0.85
HTTP_5XX_CRIT = 10
HTTP_5XX_RATIO_CRIT = 0.05
ERRLOG_CRIT = 8
RSS_WARN = 1024 ** 3
RSS_CRIT = int(2.5 * 1024 ** 3)
FD_OK = 0.70
FD_CRIT = 0.90

_LEVEL_RANK = {"skip": -1, "ok": 0, "warn": 1, "crit": 2}
_sample_lock = threading.Lock()
_last_requests: Optional[tuple] = None
_last_dropped: Optional[tuple] = None
_nginx_version_cache: dict = {"at": 0.0, "value": ""}


def collect_status() -> dict:
    """汇总一次采样。任何单项失败都不会让整个接口报错。"""
    started = time.perf_counter()
    host = _guard(collect_host, {"hostname": socket.gethostname(), "disks": [], "load": []})
    process = _guard(collect_process, {"pid": os.getpid()})
    nginx = _guard(collect_nginx, {"expected": False, "reachable": False, "config": {}})
    app = _guard(collect_app, {})
    checks = build_checks(host, process, nginx, app)
    return {
        "success": True,
        "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "verdict": summarize(checks),
        "checks": checks,
        "host": host,
        "process": process,
        "nginx": nginx,
        "app": app,
    }


def summarize(checks: list) -> dict:
    considered = [item for item in checks if item.get("level") in {"ok", "warn", "crit"}]
    worst = "ok"
    for item in considered:
        if _LEVEL_RANK[item["level"]] > _LEVEL_RANK[worst]:
            worst = item["level"]
    counts = {
        "ok": sum(1 for item in checks if item.get("level") == "ok"),
        "warn": sum(1 for item in checks if item.get("level") == "warn"),
        "crit": sum(1 for item in checks if item.get("level") == "crit"),
        "skip": sum(1 for item in checks if item.get("level") == "skip"),
    }
    level = {"ok": "stable", "warn": "watch", "crit": "unstable"}[worst]
    if worst == "crit":
        summary = f"{counts['crit']} 项超出稳定范围，需要处理"
    elif worst == "warn":
        summary = f"{counts['warn']} 项需要留意，服务仍在运行"
    else:
        summary = "各项指标都在稳定区间"
    return {"level": level, "summary": summary, "counts": counts}


def build_checks(host: dict, process: dict, nginx: dict, app: dict) -> list:
    checks = [
        _check_load(host),
        _check_cpu(host),
        _check_memory(host),
        _check_swap(host),
        *_check_disks(host),
        _check_rss(process),
        _check_fds(process),
        _check_nginx_process(nginx),
        _check_nginx_connections(nginx),
        _check_nginx_dropped(nginx),
        _check_nginx_http(nginx),
        _check_nginx_errors(nginx),
        _check_engine(app),
        _check_engine_pool(app),
        _check_jobs(app),
    ]
    order = {"crit": 0, "warn": 1, "ok": 2, "skip": 3}
    return sorted(checks, key=lambda item: (order.get(item["level"], 9), item["label"]))


# ---------------------------------------------------------------- 主机


def collect_host() -> dict:
    cpu_count = os.cpu_count() or 1
    try:
        load = [round(value, 2) for value in os.getloadavg()]
    except OSError:
        load = []
    memory = _collect_memory()
    return {
        "hostname": socket.gethostname(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": cpu_count,
        "cpu_percent": _collect_cpu_percent(cpu_count),
        "uptime_seconds": _collect_uptime(),
        "load": load,
        "memory": memory,
        "disks": _collect_disks(),
    }


def collect_process() -> dict:
    pid = os.getpid()
    rss = None
    raw = _run(["ps", "-o", "rss=", "-p", str(pid)]).strip()
    if raw.isdigit():
        rss = int(raw) * 1024
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    return {
        "pid": pid,
        "rss": rss,
        "threads": threading.active_count(),
        "uptime_seconds": max(0, int(time.time() - PROCESS_STARTED)),
        "open_fds": _open_fds(),
        "nofile_soft": _finite_limit(soft),
        "nofile_hard": _finite_limit(hard),
    }


def _collect_memory() -> dict:
    if Path("/proc/meminfo").is_file():
        return _memory_linux()
    if platform.system() == "Darwin":
        return _memory_darwin()
    return {}


def _memory_linux() -> dict:
    info: dict = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if not parts or not parts[0].isdigit():
            continue
        info[key] = int(parts[0]) * 1024
    total = info.get("MemTotal") or 0
    available = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - available)
    swap_total = info.get("SwapTotal") or 0
    swap_used = max(0, swap_total - (info.get("SwapFree") or 0))
    return _memory_payload(total, used, available, swap_total, swap_used)


def _memory_darwin() -> dict:
    total_raw = _run(["sysctl", "-n", "hw.memsize"]).strip()
    total = int(total_raw) if total_raw.isdigit() else 0
    vm = _run(["vm_stat"])
    if not total or not vm.strip():
        return {}
    page = 4096
    page_match = re.search(r"page size of (\d+) bytes", vm)
    if page_match:
        page = int(page_match.group(1))

    def pages(name: str) -> int:
        match = re.search(rf"^{re.escape(name)}:\s+(\d+)", vm, re.M)
        return int(match.group(1)) if match else 0

    available = (pages("Pages free") + pages("Pages inactive") + pages("Pages speculative")) * page
    if total and available > total:
        available = total
    used = max(0, total - available) if total else 0
    swap_raw = _run(["sysctl", "-n", "vm.swapusage"])
    swap_total = _swap_bytes(swap_raw, "total")
    swap_used = _swap_bytes(swap_raw, "used")
    return _memory_payload(total, used, available, swap_total, swap_used)


def _memory_payload(total: int, used: int, available: int, swap_total: int, swap_used: int) -> dict:
    return {
        "total": total,
        "used": used,
        "available": available,
        "percent": round(used / total * 100, 1) if total else None,
        "swap_total": swap_total,
        "swap_used": swap_used,
        "swap_percent": round(swap_used / swap_total * 100, 1) if swap_total else None,
    }


def _swap_bytes(raw: str, label: str) -> int:
    match = re.search(rf"{label}\s*=\s*([0-9.]+)([KMG])", raw)
    if not match:
        return 0
    scale = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[match.group(2)]
    return int(float(match.group(1)) * scale)


def _collect_cpu_percent(cpu_count: int) -> Optional[float]:
    if Path("/proc/stat").is_file():
        return _cpu_linux()
    if platform.system() == "Darwin":
        return _cpu_darwin(cpu_count)
    return None


def _cpu_linux() -> Optional[float]:
    first = _linux_cpu_times()
    if first is None:
        return None
    time.sleep(0.2)
    second = _linux_cpu_times()
    if second is None:
        return None
    total_delta = second[0] - first[0]
    idle_delta = second[1] - first[1]
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 1)


def _linux_cpu_times() -> Optional[tuple]:
    try:
        line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    except OSError:
        return None
    parts = line.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    nums = [int(part) for part in parts[1:] if part.isdigit()]
    if len(nums) < 4:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return sum(nums), idle


def _cpu_darwin(cpu_count: int) -> Optional[float]:
    raw = _run(["ps", "-A", "-o", "%cpu="])
    if not raw.strip():
        return None
    total = 0.0
    for line in raw.splitlines():
        try:
            total += float(line.strip())
        except ValueError:
            continue
    if cpu_count <= 0:
        return None
    return round(max(0.0, min(100.0, total / cpu_count)), 1)


def _collect_uptime() -> Optional[int]:
    if Path("/proc/uptime").is_file():
        try:
            return int(float(Path("/proc/uptime").read_text().split()[0]))
        except (OSError, ValueError, IndexError):
            return None
    raw = _run(["sysctl", "-n", "kern.boottime"])
    match = re.search(r"sec\s*=\s*(\d+)", raw)
    if not match:
        return None
    return max(0, int(time.time()) - int(match.group(1)))


def _collect_disks() -> list:
    candidates = [Path("/"), Path(GAME_DATA_DIR)]
    seen = set()
    disks = []
    for path in candidates:
        try:
            device = os.stat(path).st_dev
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        if device in seen or usage.total <= 0:
            continue
        seen.add(device)
        disks.append(
            {
                "path": "/" if path == Path("/") else str(path),
                "label": "系统盘" if path == Path("/") else "对局数据盘",
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": round(usage.used / usage.total * 100, 1),
            }
        )
    return disks


def _open_fds() -> Optional[int]:
    for candidate in ("/proc/self/fd", "/dev/fd"):
        if not os.path.isdir(candidate):
            continue
        try:
            return len(os.listdir(candidate))
        except OSError:
            return None
    return None


def _finite_limit(value: int) -> Optional[int]:
    infinity = getattr(resource, "RLIM_INFINITY", None)
    if infinity is not None and value >= infinity:
        return None
    if value < 0:
        return None
    return int(value)


# ---------------------------------------------------------------- Nginx


def collect_nginx() -> dict:
    conf_path = _nginx_conf_path()
    config = _parse_nginx_conf(conf_path) if conf_path else {}
    status_url = _nginx_status_url()
    expected = bool(status_url or conf_path)
    stub, stub_error = _fetch_stub(status_url) if status_url else (None, "")
    master_pid = _read_pid(config.get("pid", ""))
    master_alive = None
    workers = None
    if master_pid:
        master_alive = _pid_alive(master_pid)
        if master_alive:
            workers = _child_count(master_pid)
    connections = None
    if stub:
        dropped = max(0, stub["accepts"] - stub["handled"])
        connections = {
            **stub,
            "dropped_total": dropped,
            "requests_per_sec": _rate(stub["requests"]),
            "dropped_delta": _delta(dropped),
        }
    logs = _collect_nginx_logs(config) if config else None
    return {
        "expected": expected,
        "reachable": stub is not None,
        "status_url": status_url,
        "error": stub_error,
        "version": _nginx_version() if expected else "",
        "config_path": str(conf_path) if conf_path else "",
        "config": {
            "worker_processes": config.get("worker_processes") or "",
            "worker_connections": _to_int(config.get("worker_connections")),
            "listen": config.get("listen") or "",
            "gzip": config.get("gzip") or "",
            "client_max_body_size": config.get("client_max_body_size") or "",
            "server_tokens": config.get("server_tokens") or "",
        },
        "master_pid": master_pid,
        "master_alive": master_alive,
        "workers": workers,
        "connections": connections,
        "logs": logs,
    }


def _nginx_conf_path() -> Optional[Path]:
    explicit = os.environ.get("CHESS_NGINX_CONF", "").strip()
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(REPO_ROOT / ".run" / "nginx" / "nginx.conf")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _nginx_status_url() -> str:
    explicit = os.environ.get("NGINX_STATUS_URL", "").strip()
    if explicit:
        return explicit
    conf = _nginx_conf_path()
    if conf is not None:
        try:
            if "127.0.0.1:8157" in conf.read_text(encoding="utf-8", errors="replace"):
                return "http://127.0.0.1:8157/nginx_status"
        except OSError:
            pass
    serve_env = REPO_ROOT / ".run" / "serve.env"
    if not serve_env.is_file():
        return ""
    port = ""
    try:
        for line in serve_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("MACMINI_PORT="):
                port = line.split("=", 1)[1].strip()
    except OSError:
        return ""
    if port.isdigit():
        return f"http://127.0.0.1:{port}/nginx_status"
    return ""


def _parse_nginx_conf(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    def grab(pattern: str) -> str:
        match = re.search(pattern, text, re.M)
        return match.group(1).strip() if match else ""

    access_log = grab(r"^\s*access_log\s+\"?([^\"\s;]+)")
    error_log = grab(r"^\s*error_log\s+\"?([^\"\s;]+)")
    return {
        "worker_processes": grab(r"^\s*worker_processes\s+([^;]+);").strip(";"),
        "worker_connections": grab(r"^\s*worker_connections\s+(\d+);"),
        "listen": grab(r"^\s*listen\s+([^;]+);").rstrip(";").strip(),
        "gzip": "on" if re.search(r"^\s*gzip\s+on\s*;", text, re.M) else "",
        "client_max_body_size": grab(r"^\s*client_max_body_size\s+(\S+);"),
        "server_tokens": grab(r"^\s*server_tokens\s+(\S+);"),
        "pid": grab(r"^\s*pid\s+\"?([^\"\s;]+)"),
        "error_log": "" if error_log == "off" else error_log,
        "access_log": "" if access_log == "off" else access_log,
    }


def _fetch_stub(url: str) -> tuple:
    request = urllib.request.Request(url, headers={"User-Agent": "z-chess-status", "Accept": "text/plain"})
    try:
        with urllib.request.urlopen(request, timeout=1.2) as response:
            body = response.read(8192).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - 状态页要给出原因而不是 500
        return None, str(exc)
    parsed = _parse_stub(body)
    if parsed is None:
        return None, "响应不是 stub_status"
    return parsed, ""


def _parse_stub(body: str) -> Optional[dict]:
    match = re.search(
        r"Active connections:\s+(\d+)\s+"
        r"server accepts handled requests\s+"
        r"(\d+)\s+(\d+)\s+(\d+)\s+"
        r"Reading:\s+(\d+)\s+Writing:\s+(\d+)\s+Waiting:\s+(\d+)",
        body,
        re.I,
    )
    if not match:
        return None
    names = ("active", "accepts", "handled", "requests", "reading", "writing", "waiting")
    return {name: int(match.group(index)) for index, name in enumerate(names, start=1)}


def _collect_nginx_logs(config: dict) -> Optional[dict]:
    now = datetime.now()
    errors = _scan_error_log(config.get("error_log") or "", now)
    access = _scan_access_log(config.get("access_log") or "", now)
    if errors is None and access is None:
        return None
    payload = {
        "window_seconds": int(LOG_WINDOW.total_seconds()),
        "error_recent": None,
        "warn_recent": None,
        "latest_error": "",
        "http_total_recent": None,
        "http_5xx_recent": None,
    }
    if errors is not None:
        payload.update(errors)
    if access is not None:
        payload.update(access)
    return payload


def _scan_error_log(path: str, now: datetime) -> Optional[dict]:
    text = _tail_text(path)
    if text is None:
        return None
    pattern = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\s+\[(\w+)\]\s*(.*)$")
    errors = 0
    warnings = 0
    latest = ""
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        try:
            stamp = datetime.strptime(match.group(1), "%Y/%m/%d %H:%M:%S")
        except ValueError:
            continue
        if now - stamp > LOG_WINDOW:
            continue
        level = match.group(2)
        if level in {"error", "crit", "alert", "emerg"}:
            errors += 1
            latest = _redact(match.group(3))
        elif level == "warn":
            warnings += 1
    return {"error_recent": errors, "warn_recent": warnings, "latest_error": latest}


def _scan_access_log(path: str, now: datetime) -> Optional[dict]:
    text = _tail_text(path)
    if text is None:
        return None
    pattern = re.compile(r"\[(\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}) [^\]]+\] \"[A-Z]+ \S+ [^\"]*\" (\d{3})\b")
    total = 0
    server_errors = 0
    for line in text.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        try:
            stamp = datetime.strptime(match.group(1), "%d/%b/%Y:%H:%M:%S")
        except ValueError:
            continue
        if now - stamp > LOG_WINDOW:
            continue
        total += 1
        if int(match.group(2)) >= 500:
            server_errors += 1
    return {"http_total_recent": total, "http_5xx_recent": server_errors}


def _nginx_version() -> str:
    now = time.monotonic()
    if now - _nginx_version_cache["at"] < 60:
        return _nginx_version_cache["value"]
    value = ""
    try:
        proc = subprocess.run(
            ["nginx", "-v"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        value = (proc.stderr or proc.stdout or "").strip().replace("nginx version: ", "")
    except (OSError, subprocess.TimeoutExpired):
        value = ""
    _nginx_version_cache["at"] = now
    _nginx_version_cache["value"] = value
    return value


def _read_pid(path: str) -> Optional[int]:
    if not path:
        return None
    try:
        raw = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(raw) if raw.isdigit() else None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _child_count(parent: int) -> Optional[int]:
    raw = _run(["ps", "-ax", "-o", "ppid=,command="])
    if not raw.strip():
        return None
    count = 0
    for line in raw.splitlines():
        parts = line.split(None, 1)
        if parts and parts[0] == str(parent):
            count += 1
    return count


def _rate(total: int) -> Optional[float]:
    global _last_requests
    now = time.monotonic()
    with _sample_lock:
        prev = _last_requests
        _last_requests = (now, total)
    if prev is None:
        return None
    elapsed = now - prev[0]
    delta = total - prev[1]
    if elapsed < 0.5 or delta < 0:
        return None
    return round(delta / elapsed, 2)


def _delta(total: int) -> Optional[int]:
    global _last_dropped
    now = time.monotonic()
    with _sample_lock:
        prev = _last_dropped
        _last_dropped = (now, total)
    if prev is None:
        return None
    if now - prev[0] < 0.5:
        return None
    return max(0, total - prev[1])


# ---------------------------------------------------------------- 应用


def collect_app() -> dict:
    from app.engine.analysis import cache_stats
    from app.engine.jobs import get_job_manager
    from app.engine.pool import get_pool
    from app.game.hub import get_hub
    from app.game.registry import get_registry
    from app.game.storage import storage_info

    cache = cache_stats()
    lookups = cache.get("hits", 0) + cache.get("misses", 0)
    cache = {
        **cache,
        "hit_rate": round(cache.get("hits", 0) / lookups, 3) if lookups else None,
    }
    engine = get_pool().stats()
    jobs = get_job_manager().stats()
    return {
        "listen": f"{SERVER_HOST}:{get_env_port()}",
        "engine": engine,
        "jobs": {**jobs, "max": ANALYSIS_JOBS_MAX},
        "games": get_registry().stats(),
        "realtime": get_hub().stats(),
        "analysis_cache": cache,
        "storage": storage_info(),
        "config": {
            "engine_pool_size": ENGINE_POOL_SIZE,
            "engine_hash_mb": ENGINE_HASH_MB,
            "engine_threads": ENGINE_THREADS,
            "analysis_depth": POSITION_DEPTH,
            "broadcast_depth": BROADCAST_DEPTH,
            "pgn_depth": PGN_ANALYSIS_DEPTH,
            "analysis_jobs_max": ANALYSIS_JOBS_MAX,
            "analysis_cache_size": ANALYSIS_CACHE_SIZE,
        },
    }


# ---------------------------------------------------------------- 判定


def _check_load(host: dict) -> dict:
    load = host.get("load") or []
    cpus = host.get("cpu_count") or 0
    if len(load) < 3 or not cpus:
        return _item("load", "host", "系统负载", "skip", "—", "读不到负载", "1 分钟负载 / 核数 < 0.7 稳定，≥ 1.2 不稳定")
    ratio = load[0] / cpus
    level = _three(ratio, LOAD_OK, LOAD_CRIT)
    detail = f"1 分钟 {load[0]:.2f} · 5 分钟 {load[1]:.2f} · 15 分钟 {load[2]:.2f}"
    if level == "ok" and load[0] > max(load[2] * 2, cpus * 0.5) and ratio >= 0.5:
        level = "warn"
        detail += " · 短期负载明显高于 15 分钟基线"
    return _item(
        "load",
        "host",
        "系统负载",
        level,
        f"{load[0]:.2f} / {cpus} 核",
        detail,
        "1 分钟负载 / 核数 < 0.7 稳定，≥ 1.2 不稳定",
    )


def _check_cpu(host: dict) -> dict:
    percent = host.get("cpu_percent")
    if percent is None:
        return _item("cpu", "host", "CPU 占用", "skip", "—", "当前系统读不到 CPU 占用", "低于 70% 稳定，达到 90% 不稳定")
    return _item(
        "cpu",
        "host",
        "CPU 占用",
        _three(percent, CPU_OK, CPU_CRIT),
        f"{percent:.0f}%",
        f"{host.get('cpu_count') or '—'} 核",
        "低于 70% 稳定，达到 90% 不稳定",
    )


def _check_memory(host: dict) -> dict:
    memory = host.get("memory") or {}
    percent = memory.get("percent")
    if percent is None:
        return _item("memory", "host", "内存占用", "warn", "—", "未能读取内存", "低于 75% 稳定，达到 90% 不稳定")
    return _item(
        "memory",
        "host",
        "内存占用",
        _three(percent, MEM_OK, MEM_CRIT),
        f"{percent:.0f}%",
        f"已用 {_fmt_bytes(memory.get('used'))} / {_fmt_bytes(memory.get('total'))}",
        "低于 75% 稳定，达到 90% 不稳定",
    )


def _check_swap(host: dict) -> dict:
    memory = host.get("memory") or {}
    total = memory.get("swap_total") or 0
    if not total:
        return _item("swap", "host", "交换分区", "ok", "未启用", "没有配置交换空间", "低于 10% 稳定，达到 40% 不稳定")
    percent = memory.get("swap_percent") or 0
    return _item(
        "swap",
        "host",
        "交换分区",
        _three(percent, SWAP_OK, SWAP_CRIT),
        f"{percent:.0f}%",
        f"已用 {_fmt_bytes(memory.get('swap_used'))} / {_fmt_bytes(total)}",
        "低于 10% 稳定，达到 40% 不稳定",
    )


def _check_disks(host: dict) -> list:
    disks = host.get("disks") or []
    if not disks:
        return [_item("disk", "host", "磁盘空间", "warn", "—", "未能读取磁盘", "低于 80% 稳定，达到 92% 或不剩 512 MB 不稳定")]
    checks = []
    for index, disk in enumerate(disks):
        percent = disk.get("percent") or 0
        free = disk.get("free") or 0
        level = _three(percent, DISK_OK, DISK_CRIT)
        if free < DISK_FREE_CRIT:
            level = "crit"
        checks.append(
            _item(
                f"disk-{index}",
                "host",
                disk.get("label") or "磁盘空间",
                level,
                f"{percent:.0f}%",
                f"剩余 {_fmt_bytes(free)} · {disk.get('path')}",
                "低于 80% 稳定，达到 92% 或不剩 512 MB 不稳定",
            )
        )
    return checks


def _check_rss(process: dict) -> dict:
    rss = process.get("rss")
    if not rss:
        return _item("rss", "app", "API 进程内存", "skip", "—", "读不到进程内存", "低于 1 GB 稳定，达到 2.5 GB 不稳定")
    level = "ok"
    if rss >= RSS_CRIT:
        level = "crit"
    elif rss >= RSS_WARN:
        level = "warn"
    return _item(
        "rss",
        "app",
        "API 进程内存",
        level,
        _fmt_bytes(rss),
        f"PID {process.get('pid')}",
        "低于 1 GB 稳定，达到 2.5 GB 不稳定",
    )


def _check_fds(process: dict) -> dict:
    opened = process.get("open_fds")
    soft = process.get("nofile_soft")
    if not opened or not soft:
        return _item("fds", "app", "打开文件数", "skip", "—", "读不到文件描述符上限", "低于软上限的 70% 稳定，达到 90% 不稳定")
    ratio = opened / soft
    return _item(
        "fds",
        "app",
        "打开文件数",
        _three(ratio, FD_OK, FD_CRIT),
        f"{opened} / {soft}",
        f"占用软上限的 {ratio * 100:.0f}%",
        "低于软上限的 70% 稳定，达到 90% 不稳定",
    )


def _check_nginx_process(nginx: dict) -> dict:
    rule = "主进程存活，或状态接口可访问"
    if nginx.get("master_alive") is True:
        workers = nginx.get("workers")
        detail = f"主进程 {nginx.get('master_pid')}"
        if workers is not None:
            detail += f" · {workers} 个 worker"
        return _item("nginx-up", "nginx", "Nginx 进程", "ok", "运行中", detail, rule)
    if nginx.get("reachable"):
        return _item("nginx-up", "nginx", "Nginx 进程", "ok", "状态接口可达", nginx.get("version") or "连接计数可读取", rule)
    if not nginx.get("expected"):
        return _item("nginx-up", "nginx", "Nginx", "skip", "未接入", "开发环境由 Vite 直接提供页面", rule)
    if nginx.get("master_alive") is False:
        return _item("nginx-up", "nginx", "Nginx 进程", "crit", "已退出", f"pid {nginx.get('master_pid')} 不在运行", rule)
    if nginx.get("status_url"):
        return _item("nginx-up", "nginx", "Nginx 进程", "crit", "无响应", nginx.get("error") or "状态接口没有响应", rule)
    return _item("nginx-up", "nginx", "Nginx 进程", "warn", "未找到", "有配置但没有 pid 文件", rule)


def _check_nginx_connections(nginx: dict) -> dict:
    connections = nginx.get("connections") or None
    limit = (nginx.get("config") or {}).get("worker_connections")
    rule = "活跃连接 / worker_connections < 60% 稳定，≥ 85% 不稳定"
    if not nginx.get("status_url"):
        return _item("nginx-conn", "nginx", "Nginx 连接占用", "skip", "—", "未配置 stub_status", rule)
    if not connections:
        return _item("nginx-conn", "nginx", "Nginx 连接占用", "crit", "不可读", nginx.get("error") or "读不到 stub_status", rule)
    active = connections.get("active") or 0
    if not limit:
        return _item(
            "nginx-conn",
            "nginx",
            "Nginx 连接占用",
            "ok",
            str(active),
            f"读取 {connections.get('reading')} · 发送 {connections.get('writing')} · 等待 {connections.get('waiting')}",
            "未写明 worker_connections 时只展示连接数",
        )
    ratio = active / limit
    return _item(
        "nginx-conn",
        "nginx",
        "Nginx 连接占用",
        _three(ratio, NGINX_CONN_OK, NGINX_CONN_CRIT),
        f"{active} / {limit}",
        f"读取 {connections.get('reading')} · 发送 {connections.get('writing')} · 等待 {connections.get('waiting')}",
        "活跃连接 / worker_connections < 60% 稳定，≥ 85% 不稳定",
    )


def _check_nginx_dropped(nginx: dict) -> dict:
    connections = nginx.get("connections")
    if not connections:
        return _item("nginx-drop", "nginx", "连接受理", "skip", "—", "没有连接计数", "本轮出现未处理连接即不稳定")
    dropped = connections.get("dropped_total") or 0
    delta = connections.get("dropped_delta")
    detail = f"累计接受 {connections.get('accepts')}，处理 {connections.get('handled')}，未处理 {dropped}"
    if delta:
        return _item("nginx-drop", "nginx", "连接受理", "crit", f"+{delta}", detail + f" · 本轮新增 {delta}", "本轮出现未处理连接即不稳定")
    return _item("nginx-drop", "nginx", "连接受理", "ok", "正常", detail, "本轮出现未处理连接即不稳定")


def _check_nginx_http(nginx: dict) -> dict:
    logs = nginx.get("logs") or {}
    total = logs.get("http_total_recent")
    errors = logs.get("http_5xx_recent")
    if total is None:
        level = "skip"
        detail = "没有可读取的访问日志" if nginx.get("expected") else "没有 Nginx 访问日志"
        return _item("nginx-5xx", "nginx", "近 15 分钟 5xx", level, "—", detail, "0 次稳定；达到 10 次或不低于 5% 不稳定")
    if total == 0 or not errors:
        return _item("nginx-5xx", "nginx", "近 15 分钟 5xx", "ok", "0", f"样本 {total} 次请求", "0 次稳定；达到 10 次或不低于 5% 不稳定")
    ratio = errors / total
    level = "crit" if errors >= HTTP_5XX_CRIT or ratio >= HTTP_5XX_RATIO_CRIT else "warn"
    return _item(
        "nginx-5xx",
        "nginx",
        "近 15 分钟 5xx",
        level,
        str(errors),
        f"占样本 {total} 次请求的 {ratio * 100:.1f}%",
        "0 次稳定；达到 10 次或不低于 5% 不稳定",
    )


def _check_nginx_errors(nginx: dict) -> dict:
    logs = nginx.get("logs") or {}
    errors = logs.get("error_recent")
    if errors is None:
        return _item("nginx-log", "nginx", "Nginx 错误日志", "skip", "—", "没有可读取的错误日志", "近 15 分钟 0 条稳定，达到 8 条不稳定")
    warnings = logs.get("warn_recent") or 0
    detail = f"另有 {warnings} 条 warn" if warnings else "近 15 分钟没有 warn"
    latest = logs.get("latest_error") or ""
    if latest:
        detail = latest
    level = "ok"
    if errors >= ERRLOG_CRIT:
        level = "crit"
    elif errors >= 1:
        level = "warn"
    return _item("nginx-log", "nginx", "Nginx 错误日志", level, f"{errors} 条", detail, "近 15 分钟 0 条稳定，达到 8 条不稳定")


def _check_engine(app: dict) -> dict:
    engine = app.get("engine") or {}
    if not engine:
        return _item("engine", "app", "Stockfish", "warn", "—", "读不到引擎状态", "可执行文件存在才算稳定")
    if engine.get("available"):
        return _item("engine", "app", "Stockfish", "ok", "就绪", engine.get("path") or "", "可执行文件存在才算稳定")
    return _item("engine", "app", "Stockfish", "crit", "不可用", engine.get("path") or "未找到可执行文件", "可执行文件存在才算稳定")


def _check_engine_pool(app: dict) -> dict:
    engine = app.get("engine") or {}
    if not engine.get("available"):
        return _item("engine-pool", "app", "引擎池", "skip", "—", "引擎不可用", "仍有空闲实例为稳定，全部占满为留意")
    size = engine.get("pool_size") or 0
    idle = engine.get("idle") or 0
    instances = engine.get("instances") or 0
    level = "warn" if size and instances >= size and idle == 0 else "ok"
    return _item(
        "engine-pool",
        "app",
        "引擎池",
        level,
        f"空闲 {idle}",
        f"已创建 {instances} / 上限 {size}",
        "仍有空闲实例为稳定；实例已满且没有空闲为留意",
    )


def _check_jobs(app: dict) -> dict:
    jobs = app.get("jobs") or {}
    if not jobs:
        return _item("jobs", "app", "分析任务", "skip", "—", "读不到任务队列", "未达并发上限为稳定，打满为留意")
    active = jobs.get("active") or 0
    limit = jobs.get("max") or 0
    level = "warn" if limit and active >= limit else "ok"
    return _item(
        "jobs",
        "app",
        "分析任务",
        level,
        f"{active} / {limit or '—'}",
        f"队列中共 {jobs.get('total') or 0} 个任务",
        "未达并发上限为稳定，打满为留意",
    )


def _three(value: float, ok_below: float, crit_at: float) -> str:
    if value >= crit_at:
        return "crit"
    if value >= ok_below:
        return "warn"
    return "ok"


def _item(check_id: str, group: str, label: str, level: str, value: str, detail: str, rule: str) -> dict:
    return {
        "id": check_id,
        "group": group,
        "label": label,
        "level": level,
        "value": value,
        "detail": detail,
        "rule": rule,
    }


# ---------------------------------------------------------------- 工具


def _fmt_bytes(value: Optional[int]) -> str:
    if value is None:
        return "—"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(amount)} B"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def _tail_text(path: str) -> Optional[str]:
    if not path:
        return None
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
        with file_path.open("rb") as handle:
            if size > LOG_TAIL_BYTES:
                handle.seek(size - LOG_TAIL_BYTES)
                handle.readline()
            data = handle.read(LOG_TAIL_BYTES + 4096)
    except OSError:
        return None
    return data.decode("utf-8", "replace")


def _redact(text: str) -> str:
    cleaned = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "x.x.x.x", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:180]


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _run(args: list) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout or ""


def _guard(fn: Callable, fallback: dict) -> dict:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - 单项采集失败仍返回其余指标
        logger.warning("采集 %s 失败：%s", fn.__name__, exc)
        return {**fallback, "error": str(exc)}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(collect_status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
