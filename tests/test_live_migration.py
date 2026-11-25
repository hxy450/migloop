"""--live 盯整次迁移:新会话能被发现、ECAT 轮次挂得上、刷新只读增量、停止后的最终页带总览。"""

from __future__ import annotations

import json
from pathlib import Path

from migloop.live import migration


def _rec(ts: str, rtype: str, content, cwd: str, sid: str) -> dict:
    msg = {"role": rtype, "content": content}
    if rtype == "assistant":
        msg.update(id="m-" + ts, model="glm-5.3", usage={"input_tokens": 3, "output_tokens": 5})
    return {"type": rtype, "timestamp": ts, "sessionId": sid, "cwd": cwd, "message": msg,
            **({"promptSource": "typed"} if rtype == "user" else {})}


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _setup(tmp_path: Path):
    harmony = tmp_path / "proj"
    harmony.mkdir()
    croot = tmp_path / "claude" / "projects"
    slug = croot / migration.claude_slug(str(harmony))
    _write(slug / "aaaa.jsonl", [_rec("2026-11-25T10:00:00Z", "user", "迁移", str(harmony), "aaaa"),
                                 _rec("2026-11-25T10:00:05Z", "assistant", [{"type": "text", "text": "ok"}], str(harmony), "aaaa")])
    mon = migration.MigrationMonitor(str(harmony), cache_dir=str(tmp_path / "cache"), claude_root=str(croot),
                                     codex_root=str(tmp_path / "codex"), deveco_root=str(tmp_path / "nodb"),
                                     dsh_root=str(tmp_path / "dsh"))
    return harmony, slug, mon


def test_new_session_in_the_directory_is_discovered(tmp_path: Path) -> None:
    harmony, slug, mon = _setup(tmp_path)
    mon.poll_once()
    assert set(mon.slots) == {"aaaa"}
    _write(slug / "bbbb.jsonl", [_rec("2026-11-25T11:00:00Z", "user", "中途新开的会话", str(harmony), "bbbb")])
    mon.poll_once()
    assert set(mon.slots) == {"aaaa", "bbbb"}
    ids = [s["session_id"] for s in mon.overview()["sessions"]]
    assert ids == ["aaaa", "bbbb"]


def test_ecat_rounds_are_attached_to_their_run(tmp_path: Path) -> None:
    harmony, _slug, mon = _setup(tmp_path)
    run = harmony / ".migbot" / "ecat_runs" / "run_1"
    run.mkdir(parents=True)
    (run / "entropy_history.jsonl").write_text(
        "".join(json.dumps({"iteration": i, "total_H": 1.0 / i, "breakdown": {"ui": 0.5 / i},
                            "timestamp": "2026-11-25T12:0%d:00Z" % i}) + "\n" for i in (1, 2)), encoding="utf-8")
    gen = harmony / ".ecat" / "agents" / "generator" / "projects" / migration.claude_slug(str(harmony)) / "gggg.jsonl"
    _write(gen, [_rec("2026-11-25T12:05:00Z", "user", "ECAT adversarial loop (iteration 2) …", str(harmony), "gggg")])
    mon.poll_once()
    data = mon.overview()
    row = next(s for s in data["sessions"] if s["session_id"] == "run_1")
    (thread,) = row["threads"]
    assert (thread["thread_id"], thread["role"], thread["ecat_iterations"]) == ("gggg", "generator", [2])
    assert [it["iteration"] for it in data["ecat_runs"][0]["iterations"]] == [1, 2]


def test_refresh_reads_only_the_appended_bytes(tmp_path: Path) -> None:
    harmony, slug, mon = _setup(tmp_path)
    mon.poll_once()
    path = slug / "aaaa.jsonl"
    extra = json.dumps(_rec("2026-11-25T10:01:00Z", "user", "继续", str(harmony), "aaaa")) + "\n"
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(extra)
    assert mon.poll_once()
    snap = mon.slots["aaaa"]["monitor"].snapshot()
    assert snap["bytes_read_last"] == len(extra.encode("utf-8"))
    assert snap["bytes_read_total"] == path.stat().st_size
    assert not mon.poll_once(), "没有新内容时不算变化"


def test_final_page_carries_the_overview(tmp_path: Path) -> None:
    _harmony, _slug, mon = _setup(tmp_path)
    mon.poll_once()
    out = tmp_path / "out" / "final.html"
    migration.write_final(mon, str(out), build_report=lambda path: b"<html>report</html>")
    page = out.read_text(encoding="utf-8")
    boot = json.loads(page.split("window.__MIGLOOP_CHAIN__=", 1)[1].split(";</script>", 1)[0])
    (thread,) = boot["inline"]["sessions"][0]["threads"]
    assert thread["thread_id"] == "aaaa" and thread["href"] == "final.sessions/aaaa.html"
    assert (out.parent / "final.sessions" / "aaaa.html").read_bytes() == b"<html>report</html>"
    assert "会话总览" in page


def test_overview_counts_agents_per_stage_from_dispatches(tmp_path: Path) -> None:
    harmony, slug, mon = _setup(tmp_path)
    h = str(harmony)
    agent = {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"description": "worker", "prompt": "p"}}
    rows = [_rec("2026-11-25T10:00:00Z", "user", "<command-name>/a2h-spec</command-name>", h, "aaaa"),
            _rec("2026-11-25T10:02:00Z", "assistant", [{"type": "text", "text": "spec"}], h, "aaaa"),
            _rec("2026-11-25T10:03:00Z", "assistant", [agent], h, "aaaa")]
    _write(slug / "aaaa.jsonl", rows)
    mon.poll_once()
    (thread,) = mon.overview()["sessions"][0]["threads"]
    assert [(st["label"], st["agents"]) for st in thread["stages"]] == [("Spec", 1)]
    from migloop.render import load_asset
    assert "实时不统计" in load_asset("chain.html")      # 老 checkpoint 没记派发数的段显示「—」


def test_final_page_writes_the_overview_before_the_slow_details(tmp_path: Path) -> None:
    import signal
    _harmony, _slug, mon = _setup(tmp_path)
    mon.poll_once()
    out = tmp_path / "out" / "final.html"
    seen = []

    def build_report(path: str) -> bytes:
        seen.append(out.is_file() and ".sessions/" not in out.read_text(encoding="utf-8"))
        return b"<html>report</html>"            # 关窗口只给几秒:先有总览(还没链到没写好的详情),再逐个写详情

    migration.write_final(mon, str(out), build_report=build_report)
    assert seen == [True] and "final.sessions/" in out.read_text(encoding="utf-8")
    if hasattr(signal, "SIGBREAK"):                     # Windows:Ctrl+Break 也照常写最终页
        old = signal.getsignal(signal.SIGBREAK)
        try:
            migration.install_stop_signals()
            assert signal.getsignal(signal.SIGBREAK) is migration._stop_signal
        finally:
            signal.signal(signal.SIGBREAK, old)
    # 关窗口:打断主线程一次,然后等最终页写完才返回(系统在处理函数返回后就结束进程)
    import threading
    stopper, calls = migration.Stopper(), []
    threading.Timer(0.2, stopper.done.set).start()
    assert stopper.on_console_close(lambda: calls.append(1), wait=5) is True
    assert calls == [1] and stopper.done.is_set()
    stopper.stopping.set()                              # 已在停止(正在写最终页)时不再打断
    assert stopper.on_console_close(lambda: calls.append(2), wait=0) is True and calls == [1]


def test_agent_count_shows_dispatches_with_transcripts_when_fewer(tmp_path: Path) -> None:
    from migloop import chain
    from migloop.render import load_asset
    trace = {"meta": {}, "totals": {"agent_calls": 52, "subagent_transcripts": 5}, "stages": [], "tools": [],
             "agents": [], "prompts": []}
    row = chain.summarize(trace)
    assert (row["agents"], row["agents_with_transcript"]) == (52, 5)
    harmony, slug, mon = _setup(tmp_path)              # live:派发 1 次,还没有子代理转录
    h = str(harmony)
    agent = {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"description": "worker", "prompt": "p"}}
    _write(slug / "aaaa.jsonl", [_rec("2026-11-25T10:00:00Z", "assistant", [agent], h, "aaaa")])
    mon.poll_once()
    (thread,) = mon.overview()["sessions"][0]["threads"]
    assert (thread["agents"], thread["agents_with_transcript"]) == (1, 0)
    assert '"(有转录 "' in load_asset("chain.html")      # 总览:52(有转录 5);相等时只一个数
    assert '"(有转录 "' in load_asset("viewer.html")     # 离线页页头统计


def test_failed_dispatch_is_not_counted_live(tmp_path: Path) -> None:
    harmony, slug, mon = _setup(tmp_path)
    h = str(harmony)
    agent = {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"description": "worker", "prompt": "p"}}
    error = {"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "Agent type 'x' not found"}
    _write(slug / "aaaa.jsonl", [_rec("2026-11-25T10:00:00Z", "assistant", [agent], h, "aaaa"),
                                 _rec("2026-11-25T10:00:01Z", "user", [error], h, "aaaa")])
    mon.poll_once()
    (thread,) = mon.overview()["sessions"][0]["threads"]
    assert (thread["agents"], thread["agents_with_transcript"]) == (0, 0)   # 报错的派发没生成子代理
