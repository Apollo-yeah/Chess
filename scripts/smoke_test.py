#!/usr/bin/env python3
"""端到端验收测试（仅依赖 tornado，标准库级别的依赖）。

覆盖：
  1. 健康检查与引擎可用性
  2. 多对局隔离（A 局走棋不影响 B 局）
  3. 服务端规则校验（非法走法、轮次归属、不存在的对局）
  4. 悔棋 / 重置 / 历史列表
  5. WebSocket 两段式推送（status_update → analysis_update）
  6. **引擎计算不阻塞 IOLoop**（长棋谱任务运行期间接口仍然秒回）
  7. 长棋谱异步任务：进度、取消、结果
  8. 终局落盘 + PGN 导出（文件名不含冒号）
  9. 旧数据结构兼容（沿用历史 JSON 目录时能正常加载）

用法::

    PORT=8199 CHESS_DATA_DIR=/tmp/zc/data CHESS_PGN_DIR=/tmp/zc/pgn python3 -m app &
    python3 scripts/smoke_test.py http://127.0.0.1:8199
    # 追加第二个参数即可额外验证「经 Vite preview / Nginx 代理」的链路
    python3 scripts/smoke_test.py http://127.0.0.1:8199 http://127.0.0.1:4173
"""

import asyncio
import json
import os
import sys
import time

from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.websocket import websocket_connect

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8199").rstrip("/")
WS_BASE = BASE.replace("http://", "ws://").replace("https://", "wss://")

INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# 4 着将杀：1. f3 e5 2. g4 Qh4#
MATE_LINE = ["f2f3", "e7e5", "g2g4", "d8h4"]
# 约 20 着的开局，用于长棋谱分析任务
LONG_PGN = """[Event "Smoke"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. b4 Bxb4 5. c3 Ba5 6. d4 exd4 7. O-O d3
8. Qb3 Qf6 9. e5 Qg6 10. Re1 Nge7 1-0
"""

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  \033[32mPASS\033[0m {name}")
    else:
        FAILED += 1
        print(f"  \033[31mFAIL\033[0m {name}  {detail}")
    return condition


async def api(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    client = AsyncHTTPClient()
    request = HTTPRequest(
        url=f"{BASE}{path}",
        method=method,
        headers={"Content-Type": "application/json"},
        body=json.dumps(body) if body is not None else ("{}" if method in ("POST", "PUT", "PATCH") else None),
        request_timeout=120,
    )
    response = await client.fetch(request, raise_error=False)
    try:
        payload = json.loads(response.body or b"{}")
    except json.JSONDecodeError:
        payload = {"raw": response.body.decode("utf-8", "replace")[:200]}
    return response.code, payload


async def section_health() -> None:
    print("\n[1] 健康检查")
    code, health = await api("GET", "/api/health")
    check("GET /api/health → 200", code == 200, f"code={code}")
    engine = health.get("engine", {})
    check("引擎可用（probe_ok）", engine.get("probe_ok") is True, json.dumps(engine)[:200])
    check("整体状态 ok", health.get("status") == "ok", str(health.get("status")))
    print(f"       engine: {engine.get('path')} · 池大小 {engine.get('pool_size')}")


async def section_isolation() -> tuple[str, str]:
    print("\n[2] 多对局隔离")
    _, game_a = await api("POST", "/api/games", {"mode": "self"})
    _, game_b = await api("POST", "/api/games", {"mode": "self"})
    id_a, id_b = game_a["game_id"], game_b["game_id"]
    check("两局 game_id 不同", id_a != id_b)

    code, moved = await api("POST", f"/api/games/{id_a}/move", {"move": "e2e4"})
    check("A 局走棋成功", code == 200 and moved.get("success"), json.dumps(moved)[:200])
    check("A 局 SAN 记录正确", moved.get("move_info", {}).get("san") == "e4", str(moved.get("move_info")))

    _, state_b = await api("GET", f"/api/games/{id_b}")
    check(
        "B 局完全不受影响",
        state_b["board_state"]["fen"] == INITIAL_FEN and state_b["statistics"]["total_moves"] == 0,
        state_b["board_state"]["fen"],
    )
    _, state_a = await api("GET", f"/api/games/{id_a}")
    check("A 局状态被持久化命中", state_a["statistics"]["total_moves"] == 1)
    return id_a, id_b


async def section_rules(id_a: str) -> None:
    print("\n[3] 服务端规则校验")
    # A 局此刻轮到黑方；再次走白兵 e2e4 属于非法走法
    code, payload = await api("POST", f"/api/games/{id_a}/move", {"move": "e2e4"})
    check("非法走法被拒（400）", code == 400, f"code={code} body={json.dumps(payload)[:160]}")
    check("错误信息可读", "非法走法" in payload.get("error", ""), payload.get("error", ""))

    code, payload = await api("POST", f"/api/games/{id_a}/move", {"move": "zzzz"})
    check("格式非法走法被拒", code == 400, f"code={code}")

    code, payload = await api("GET", "/api/games/does-not-exist")
    check("未知对局 → 404", code == 404, f"code={code}")

    _, game_ai = await api("POST", "/api/games", {"mode": "ai", "player_color": "white"})
    ai_id = game_ai["game_id"]
    code, payload = await api("POST", f"/api/games/{ai_id}/ai")
    check("玩家回合时 AI 不得落子", code == 400, f"code={code} {json.dumps(payload)[:160]}")

    code, payload = await api("POST", f"/api/games/{ai_id}/move", {"move": "e2e4"})
    check("玩家走棋后轮到 AI", code == 200 and payload["board_state"]["turn"] == "black")
    code, payload = await api("POST", f"/api/games/{ai_id}/ai")
    check("AI 走棋成功", code == 200 and payload.get("ai_move"), json.dumps(payload)[:200])
    check("AI 走法已记录为 ai 类型", payload.get("move_info", {}).get("type") == "ai")
    code, payload = await api("POST", f"/api/games/{ai_id}/undo", {"plies": 2})
    check("一次悔两着（AI 模式）", code == 200 and payload["statistics"]["total_moves"] == 0,
          str(payload.get("statistics")))


async def section_websocket(id_a: str) -> None:
    print("\n[5] WebSocket 两段式推送")
    connection = await websocket_connect(f"{WS_BASE}/ws/game?game_id={id_a}")
    hello = json.loads(await asyncio.wait_for(connection.read_message(), timeout=10))
    check("连接即收到 hello", hello.get("type") == "hello", str(hello)[:160])
    check("hello 携带订阅的对局", hello.get("game_id") == id_a)

    await api("POST", f"/api/games/{id_a}/move", {"move": "e7e5"})

    seen_status = None
    seen_analysis = None
    deadline = time.time() + 40
    while time.time() < deadline and (seen_status is None or seen_analysis is None):
        message = await asyncio.wait_for(connection.read_message(), timeout=40)
        if message is None:
            break
        data = json.loads(message)
        if data.get("type") == "status_update" and seen_status is None:
            seen_status = data
            board = data["status"]["board_state"]
            check(
                "状态推送先到（含 fen/turn/legal_moves）",
                board["turn"] == "white" and "d2d4" in board["legal_moves"] and board["is_check"] is False,
                json.dumps(board)[:200],
            )
            check(
                "推送的是走棋后的最新局面",
                data["status"]["move_history"][-1]["move"] == "e7e5",
                str(data["status"]["move_history"][-1:]),
            )
            check("状态推送含走法历史", len(data["status"]["move_history"]) == 2)
        elif data.get("type") == "analysis_update":
            seen_analysis = data

    check("随后补发 analysis_update（引擎结果）", seen_analysis is not None)
    if seen_analysis:
        analysis = seen_analysis["analysis"]
        check("分析成功且带白方视角分值", analysis.get("success") and isinstance(analysis.get("advantage_score"), (int, float)),
              json.dumps(analysis)[:200])
        check("分析给出最佳走法", bool(analysis.get("current_best_move")), str(analysis)[:200])
        check("分析推送携带对应局面 fen", seen_analysis.get("fen") == seen_status["status"]["board_state"]["fen"])

    connection.close()


async def _next_message(connection, predicate, timeout: float = 20):
    """读到第一条满足条件的推送，中间的分析包直接跳过。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = max(1.0, deadline - time.time())
        message = await asyncio.wait_for(connection.read_message(), timeout=remaining)
        if message is None:
            return None
        data = json.loads(message)
        if predicate(data):
            return data
    return None


async def section_live_share() -> None:
    print("\n[11] 共享当前对局")
    code, first = await api("GET", "/api/games/current")
    code2, second = await api("GET", "/api/games/current")
    check("GET /api/games/current → 200", code == 200 and code2 == 200, f"{code}/{code2}")
    live_id = first.get("game_id")
    check("两个客户端拿到同一局", bool(live_id) and live_id == second.get("game_id"), f"{live_id} vs {second.get('game_id')}")

    _, private = await api("POST", "/api/games", {"mode": "self"})
    _, still = await api("GET", "/api/games/current")
    check(
        "单独建局不替换当前局",
        still.get("game_id") == live_id and private.get("game_id") != live_id,
        f"live={still.get('game_id')} private={private.get('game_id')}",
    )

    left = await websocket_connect(f"{WS_BASE}/ws/game")
    right = await websocket_connect(f"{WS_BASE}/ws/game")
    hello_l = json.loads(await asyncio.wait_for(left.read_message(), timeout=10))
    hello_r = json.loads(await asyncio.wait_for(right.read_message(), timeout=10))
    check(
        "未指定 game_id 时两边都进入当前局",
        hello_l.get("type") == "hello"
        and hello_l.get("game_id") == live_id
        and hello_r.get("game_id") == live_id,
        f"{hello_l.get('game_id')} / {hello_r.get('game_id')}",
    )

    code, reset = await api("POST", f"/api/games/{live_id}/reset", {"mode": "self"})
    new_id = reset.get("game_id")
    check("重置当前局得到新 id", code == 201 and bool(new_id) and new_id != live_id, f"code={code} {new_id}")

    def is_new_board(data: dict) -> bool:
        info = data.get("status", {}).get("game_info", {})
        return data.get("type") == "status_update" and info.get("game_id") == new_id

    status_l, status_r = await asyncio.gather(
        _next_message(left, is_new_board),
        _next_message(right, is_new_board),
    )
    check("重置后两个连接都看到新局", status_l is not None and status_r is not None)
    if status_l:
        check("新局是初始局面", status_l["status"]["board_state"]["fen"] == INITIAL_FEN, status_l["status"]["board_state"]["fen"])

    _, after_reset = await api("GET", "/api/games/current")
    check("当前局指针已指向新局", after_reset.get("game_id") == new_id, after_reset.get("game_id"))

    code, moved = await api("POST", f"/api/games/{new_id}/move", {"move": "e2e4"})
    check("任一客户端可以走当前局", code == 200 and moved.get("success") is True, json.dumps(moved)[:180])

    def is_e4(data: dict) -> bool:
        history = data.get("status", {}).get("move_history") or []
        return data.get("type") == "status_update" and bool(history) and history[-1].get("move") == "e2e4"

    move_l, move_r = await asyncio.gather(
        _next_message(left, is_e4),
        _next_message(right, is_e4),
    )
    check("走棋后两个连接都看到 e4", move_l is not None and move_r is not None)

    _, mirrored = await api("GET", "/api/games/current")
    check(
        "再次进入仍是走完 e4 的这一局",
        mirrored.get("game_id") == new_id and mirrored.get("statistics", {}).get("total_moves") == 1,
        json.dumps(mirrored.get("statistics"))[:120],
    )

    ghost = await websocket_connect(f"{WS_BASE}/ws/game?game_id=does-not-exist")
    hello_g = json.loads(await asyncio.wait_for(ghost.read_message(), timeout=10))
    check("不存在的 game_id 改入当前局", hello_g.get("game_id") == new_id, hello_g.get("game_id"))

    named = await websocket_connect(f"{WS_BASE}/ws/game?game_id={private['game_id']}")
    hello_n = json.loads(await asyncio.wait_for(named.read_message(), timeout=10))
    check("显式 game_id 仍可订阅指定局", hello_n.get("game_id") == private["game_id"], hello_n.get("game_id"))

    left.close()
    right.close()
    ghost.close()
    named.close()


async def section_non_blocking() -> None:
    print("\n[6] 引擎计算不阻塞 IOLoop")
    code, job = await api("POST", "/api/analysis/jobs", {"pgn_text": LONG_PGN, "depth": 12})
    check("长棋谱任务提交返回 202", code == 202, f"code={code} {json.dumps(job)[:160]}")
    job_id = job["job_id"]

    # 等任务真正跑起来
    for _ in range(100):
        _, status = await api("GET", f"/api/analysis/jobs/{job_id}")
        if status.get("status") == "running":
            break
        await asyncio.sleep(0.05)

    latencies = []
    for _ in range(8):
        start = time.perf_counter()
        code, health = await api("GET", "/api/health")
        latencies.append(time.perf_counter() - start)
        check_latency_ok = code == 200
        if not check_latency_ok:
            break
        await asyncio.sleep(0.1)
    worst = max(latencies) if latencies else 99
    check(
        f"分析任务运行中接口仍秒回（最慢 {worst * 1000:.0f}ms < 1000ms）",
        worst < 1.0,
        f"latencies={[round(value * 1000) for value in latencies]}",
    )

    # 轮询到完成
    result = None
    deadline = time.time() + 180
    while time.time() < deadline:
        _, status = await api("GET", f"/api/analysis/jobs/{job_id}")
        if status.get("status") in ("done", "error", "cancelled"):
            result = status
            break
        await asyncio.sleep(0.5)
    check("长棋谱任务完成", result is not None and result.get("status") == "done",
          json.dumps(result or {})[:200])
    if result and result.get("status") == "done":
        payload = result["result"]
        # LONG_PGN 为 10 个回合 = 20 着
        check("逐着分析条数正确", len(payload["move_analysis"]) == 20, str(len(payload["move_analysis"])))
        check("进度达到 100%", result["progress"]["percent"] == 100.0, str(result["progress"]))
        check("白方视角分值符号正确（白优为正）",
              all(isinstance(item["score_value"], (int, float)) for item in payload["move_analysis"]))
        check("含关键节点数组", isinstance(payload["key_moments"], list))
        check("逐着含 SAN 记谱", all(item["move_san"] for item in payload["move_analysis"]))


async def section_job_cancel() -> None:
    print("\n[7] 任务取消")
    _, job = await api("POST", "/api/analysis/jobs", {"pgn_text": LONG_PGN, "depth": 16})
    job_id = job["job_id"]
    code, cancelled = await api("DELETE", f"/api/analysis/jobs/{job_id}")
    check("DELETE 取消返回 200", code == 200, f"code={code}")
    await asyncio.sleep(0.8)
    _, status = await api("GET", f"/api/analysis/jobs/{job_id}")
    check("任务状态为 cancelled", status.get("status") == "cancelled", str(status.get("status")))
    code, _ = await api("GET", "/api/analysis/jobs/deadbeefdeadbeef")
    check("未知任务 → 404", code == 404, f"code={code}")


async def section_finish_and_pgn() -> tuple[str, str]:
    print("\n[8] 终局落盘 + PGN 导出")
    _, game = await api("POST", "/api/games", {"mode": "self"})
    game_id = game["game_id"]
    payload = {}
    for uci in MATE_LINE:
        code, payload = await api("POST", f"/api/games/{game_id}/move", {"move": uci})
        if code != 200:
            break
    check("四着将杀执行成功", payload.get("board_state", {}).get("is_checkmate") is True,
          json.dumps(payload)[:200])
    check("结果判定为 black_win", payload.get("game_info", {}).get("result") == "black_win",
          str(payload.get("game_info", {}).get("result")))

    code, payload = await api("POST", f"/api/games/{game_id}/move", {"move": "a2a3"})
    check("终局后拒绝继续走棋", code == 400, f"code={code}")

    data_dir = os.environ.get("SMOKE_DATA_DIR")
    pgn_dir = os.environ.get("SMOKE_PGN_DIR")
    if data_dir and pgn_dir:
        json_path = os.path.join(data_dir, f"{game_id}.json")
        check("对局 JSON 已落盘", os.path.isfile(json_path), json_path)
        # 只认这一局导出的 PGN（目录里还有别的对局）
        expected = [name for name in os.listdir(pgn_dir) if game_id[:8] in name]
        check("本局 PGN 已导出", len(expected) == 1, str(expected))
        check("PGN 文件名不含冒号（Windows 安全）",
              all(":" not in name for name in os.listdir(pgn_dir)), str(os.listdir(pgn_dir)))
        if expected:
            with open(os.path.join(pgn_dir, expected[0]), "r", encoding="utf-8") as handle:
                content = handle.read()
            check("PGN 含结果与对局 ID", "[Result \"0-1\"]" in content and game_id in content, content[:160])
            check("PGN 记录了将杀走法", "Qh4#" in content, content[-80:])
    return game_id, pgn_dir or ""


async def section_reset_history() -> None:
    print("\n[4] 悔棋 / 重置 / 历史")
    _, game = await api("POST", "/api/games", {"mode": "self"})
    game_id = game["game_id"]
    for uci in ["d2d4", "d7d5", "c2c4"]:
        await api("POST", f"/api/games/{game_id}/move", {"move": uci})

    code, payload = await api("POST", f"/api/games/{game_id}/undo", {"plies": 1})
    check("悔棋一着", code == 200 and payload["statistics"]["total_moves"] == 2,
          str(payload.get("statistics")))

    code, payload = await api("POST", f"/api/games/{game_id}/reset")
    check("重置返回全新 game_id", code == 201 and payload["game_id"] != game_id,
          f"code={code} {payload.get('game_id')}")
    check("新局棋盘为初始局面", payload["board_state"]["fen"] == INITIAL_FEN)

    code, history = await api("GET", "/api/games")
    check("历史列表可用", code == 200 and history.get("game_count", 0) >= 5,
          f"count={history.get('game_count')}")
    check("历史项含摘要字段", all(
        {"game_id", "result", "total_moves"} <= set(item) for item in history["games"]
    ))


async def section_parallel_isolation() -> None:
    """多人同时访问：跨局并发互不干扰，同局并发被锁正确串行化。"""
    print("\n[10] 并发隔离")
    games_count = 8
    line = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]

    created = await asyncio.gather(
        *[api("POST", "/api/games", {"mode": "self"}) for _ in range(games_count)]
    )
    ids = [payload["game_id"] for _, payload in created]
    check(f"{games_count} 局并行创建成功", len(set(ids)) == games_count, str(ids)[:120])

    async def play(game_id: str):
        for uci in line:
            code, payload = await api("POST", f"/api/games/{game_id}/move", {"move": uci})
            if code != 200:
                return code, payload
        return 200, payload

    started = time.perf_counter()
    outcomes = await asyncio.gather(*[play(game_id) for game_id in ids])
    elapsed = time.perf_counter() - started

    check("8 局 × 6 着 全部成功", all(code == 200 for code, _ in outcomes),
          str([code for code, _ in outcomes]))
    fens = {payload["board_state"]["fen"] for _, payload in outcomes}
    check("各局走法序列一致（无串局）", len(fens) == 1, f"得到 {len(fens)} 种终局 FEN")
    check(f"并发耗时合理（{elapsed:.2f}s）", elapsed < 20, f"{elapsed:.2f}s")

    states = await asyncio.gather(*[api("GET", f"/api/games/{gid}") for gid in ids])
    check("每局各记录 6 着", all(s["statistics"]["total_moves"] == 6 for _, s in states),
          str([s["statistics"]["total_moves"] for _, s in states]))

    # 同一局并发抢同一步：per-game 锁必须只放行一个
    target = ids[0]
    results = await asyncio.gather(
        *[api("POST", f"/api/games/{target}/move", {"move": "d2d4"}) for _ in range(5)]
    )
    codes = sorted(code for code, _ in results)
    ok = codes.count(200)
    _, after = await api("GET", f"/api/games/{target}")
    check("同局并发 5 次只成功 1 次", ok == 1, f"codes={codes}")
    check("同局并发只落下一着（6 → 7）", after["statistics"]["total_moves"] == 7,
          str(after["statistics"]))
    check("其余并发请求返回可读错误", all(
        code == 400 for code, _ in results if code != 200
    ), str(codes))


async def section_proxy(web_base: str) -> None:
    """通过 Vite preview / Nginx 代理访问的集成检查（可选第二节参数）。

    重点验证 WebSocket 握手：浏览器会带上 Origin，代理后 Origin 与 API 的 Host 不同，
    必须被显式的来源白名单接受，否则实时分析板块永远连不上。
    """
    print(f"\n[9] 经代理的集成（{web_base}）")
    web = web_base.rstrip("/")

    client = AsyncHTTPClient()
    index = await client.fetch(f"{web}/", raise_error=False)
    body = index.body.decode("utf-8", "replace")
    check("首页返回 200", index.code == 200, f"code={index.code}")
    check("首页引用构建产物", "/assets/" in body and "<div id=\"root\">" in body, body[:120])

    deep = await client.fetch(f"{web}/pgn-replay", raise_error=False)
    check("SPA 深链回退到 index.html", deep.code == 200 and b"<div id=\"root\">" in deep.body,
          f"code={deep.code}")

    proxied = await client.fetch(f"{web}/api/health", raise_error=False)
    check("代理 /api 到后端", proxied.code == 200 and b'"status"' in proxied.body,
          f"code={proxied.code}")

    # 以浏览器身份带 Origin 建立 WebSocket（websocket_connect 支持传 HTTPRequest）
    origin = web
    # 无 game_id 的连接会进入当前共享局。先重置，保证后面的 d2d4 落在初始局面上。
    current_resp = await client.fetch(f"{web}/api/games/current", raise_error=False)
    current_payload = json.loads(current_resp.body or b"{}")
    check("代理可以读取当前对局", current_resp.code == 200 and bool(current_payload.get("game_id")),
          f"code={current_resp.code}")
    reset_resp = await client.fetch(
        HTTPRequest(
            url=f"{web}/api/games/{current_payload.get('game_id')}/reset",
            method="POST",
            headers={"Content-Type": "application/json", "Origin": origin},
            body=json.dumps({"mode": "self"}),
        ),
        raise_error=False,
    )
    check("代理重置当前局到初始局面", reset_resp.code == 201, f"code={reset_resp.code}")

    ws_request = HTTPRequest(
        url=f"{web.replace('http://', 'ws://')}/ws/game",
        headers={"Origin": origin},
    )
    connection = await websocket_connect(ws_request)
    hello = json.loads(await asyncio.wait_for(connection.read_message(), timeout=10))
    check(f"代理后 WebSocket 握手成功（Origin: {origin}）", hello.get("type") == "hello",
          str(hello)[:160])
    game_id = hello.get("game_id")
    check("hello 分配/回显 game_id", bool(game_id), str(hello)[:120])

    # 同样经代理触发一次走棋，确认推送链路完整
    await client.fetch(
        HTTPRequest(
            url=f"{web}/api/games/{game_id}/move",
            method="POST",
            headers={"Content-Type": "application/json", "Origin": origin},
            body=json.dumps({"move": "d2d4"}),
        )
    )
    kinds = set()
    deadline = time.time() + 40
    while time.time() < deadline and not {"status_update", "analysis_update"} <= kinds:
        message = await asyncio.wait_for(connection.read_message(), timeout=40)
        if message is None:
            break
        kinds.add(json.loads(message).get("type"))
    check("经代理收到 status_update", "status_update" in kinds, str(kinds))
    check("经代理收到 analysis_update", "analysis_update" in kinds, str(kinds))
    connection.close()


async def main() -> int:
    print(f"对端：{BASE}")
    try:
        await section_health()
        id_a, _ = await section_isolation()
        await section_rules(id_a)
        await section_reset_history()
        await section_websocket(id_a)
        await section_non_blocking()
        await section_job_cancel()
        await section_finish_and_pgn()
        await section_parallel_isolation()
        await section_live_share()
        if len(sys.argv) > 2:
            await section_proxy(sys.argv[2])
    finally:
        AsyncHTTPClient().close()

    print(f"\n结果：{PASSED} 通过 / {FAILED} 失败")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
