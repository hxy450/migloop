"""会话总览(移植自 hmigbot-plus tests/web/test_insight1_chain.py,72c56b60 / cd6d3d4e / 3fd7850d)。

elite 的链骨架是事件库的会话时间线(切链、breather 接力、能力会话按名字前缀认),那部分是产品侧,
不搬,对应用例不搬。migloop 只吃磁盘上的 transcript:同工程 root 会话 + ECAT 各 run 的角色会话。
这里钉住解析部分:角色 / 轮次 / 判官维度、提示词、汇总、阶段定位、run 目录只扫一遍、--serve 路由。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from migloop import chain, ecat, followups, serve
from migloop.adapters import claude as claude_adapter
from migloop.adapters import codex as codex_adapter

W, REVIEWER = "01a0b000-0000-7000-8000-000000000001", "01a0b964-0000-7000-8000-0000000000aa"
J0, D0, GEN, J1, D1 = (f"01a0b000-0000-7000-8000-00000000000{i}" for i in range(2, 7))
RUN_ID = "run_20260919_050306"


def _rec(minute: int, rtype: str, payload: dict) -> str:
    return json.dumps({"timestamp": f"2026-09-19T12:{minute:02d}:00.000Z", "type": rtype, "payload": payload})


def _rollout(root: Path, tid: str, cwd: str, *, start: int, prompt: str = "", fail: bool = False) -> Path:
    lines = [_rec(start, "session_meta", {"id": tid, "cwd": cwd, "cli_version": "0.147.0",
                                          "timestamp": f"2026-09-19T12:{start:02d}:00.000Z"}),
             _rec(start, "turn_context", {"model": "glm-5.3"})]
    if prompt:  # 真实 rollout 两处都记:模型输入 + 用户消息事件
        lines.append(_rec(start, "response_item", {"type": "message", "role": "user",
                                                   "content": [{"type": "input_text", "text": prompt}]}))
        lines.append(_rec(start, "event_msg", {"type": "user_message", "message": prompt}))
    lines.append(_rec(start + 1, "response_item", {"type": "function_call", "name": "exec_command",
                                                   "call_id": "c1", "arguments": json.dumps({"cmd": "ls"})}))
    lines.append(_rec(start + 1, "response_item", {
        "type": "function_call_output", "call_id": "c1",
        "output": f"Process exited with code {1 if fail else 0}\nOutput:\nx"}))
    lines.append(_rec(start + 2, "event_msg", {"type": "task_complete"}))
    path = root / "2026" / "09" / "19" / f"rollout-2026-09-19T05-{start:02d}-00-{tid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _stream(path: Path, tid: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"subtype": "init", "session_id": tid}) + "\n", encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """codex_sdk 线实测形态:角色目录没有 projects/,rollout 全落在 Codex 根,路径不带角色。"""
    harmony = tmp_path / "harmony"
    (harmony / ".ecat" / "agents" / "generator").mkdir(parents=True)
    (harmony / ".migbot").mkdir()
    (harmony / ".migbot" / "config.json").write_text(json.dumps({
        "project": "Cofi", "run_id": "f0b2ddbc", "hmigbot_session_id": "c48c34f6",
        "android": "/work/Cofi", "harmonyos": str(harmony)}), encoding="utf-8")
    run = harmony / ".migbot" / "ecat_runs" / RUN_ID
    _stream(run / "0" / "discriminator.stream.jsonl", D0)
    _stream(run / "0" / "generator.stream.jsonl", GEN)
    _stream(run / "1" / "discriminator.stream.jsonl", D1)
    _stream(run / "1" / "generator.stream.jsonl", GEN)  # generator 跨轮复用同一 thread
    _stream(run / "transcripts" / "judge_page_audit.stream.jsonl", J1)  # 判官流每轮覆盖,只剩末轮
    (run / "entropy_history.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"iteration": 0, "total_H": 0.2521, "breakdown": {"page_audit": 0.68},
         "timestamp": "2026-09-19T12:17:00+00:00"},
        {"iteration": 1, "total_H": 0.0422, "breakdown": {"page_audit": 0.24},
         "timestamp": "2026-09-19T12:40:00+00:00"}]) + "\n", encoding="utf-8")

    sessions = tmp_path / "codex" / "sessions"
    judge = "You are an automated HarmonyOS code quality evaluator for the **page_audit** dimension."
    cwd = str(harmony)
    worker = _rollout(sessions, W, cwd, start=0, fail=True)
    _rollout(sessions, REVIEWER, cwd, start=5)
    _rollout(sessions, J0, cwd, start=10, prompt=judge)
    _rollout(sessions, D0, cwd, start=17, prompt="You are the Discriminator in the ECAT adversarial loop (iteration 0).")
    _rollout(sessions, GEN, cwd, start=20, prompt="You are the Generator in the ECAT adversarial loop (iteration 0).")
    _rollout(sessions, J1, cwd, start=40, prompt=judge)
    _rollout(sessions, D1, cwd, start=50, prompt="You are the Discriminator in the ECAT adversarial loop (iteration 1).")
    _rollout(sessions, "01a0b000-0000-7000-8000-0000000000ff", str(tmp_path / "another"), start=30)
    monkeypatch.setattr(codex_adapter, "default_root", lambda: str(sessions))
    return SimpleNamespace(harmony=harmony, sessions=sessions, worker=worker)


def _threads(c: dict) -> dict[str, dict]:
    return {t["thread_id"]: t for s in c["sessions"] for t in s["threads"]}


def test_build_chain_puts_every_session_of_the_migration_in_one_place(project: SimpleNamespace) -> None:
    c = chain.build_chain(str(project.worker))

    assert (c["anchor"], c["project"], c["run_id"]) == (W, "Cofi", "f0b2ddbc")
    threads = _threads(c)
    assert set(threads) == {W, REVIEWER, J0, D0, GEN, J1, D1}, "别的工程的 rollout 不收"
    assert all(t["transcript"] for t in threads.values()), "7 个运行时会话的 transcript 都要定位到"
    assert (threads[GEN]["role"], threads[GEN]["ecat_iterations"]) == ("generator", [0, 1])
    assert (threads[D0]["role"], threads[D1]["role"]) == ("discriminator", "discriminator")
    assert (threads[J1]["role"], threads[J1]["dimension"]) == ("judge", "page_audit")
    assert (threads[J0]["role"], threads[J0]["dimension"]) == ("judge", "page_audit"), \
        "判官流文件每轮覆盖,早先轮次的判官也要认得出"
    assert threads[W]["tool_calls"] == 1 and threads[W]["tool_failed"] == 1
    kinds = {s["session_id"]: s["kind"] for s in c["sessions"]}
    assert kinds[W] == kinds[REVIEWER] == "session", "没有事件库就不猜主迁移 / 评审"
    assert kinds[RUN_ID] == "ecat"


def test_build_chain_carries_each_runtime_sessions_prompts(project: SimpleNamespace) -> None:
    """ECAT / 判官的提示词在会话总览上直接可看。"""
    threads = _threads(chain.build_chain(str(project.worker)))
    assert threads[D1]["prompts"][0]["text"].startswith("You are the Discriminator in the ECAT adversarial loop")
    assert "page_audit" in threads[J0]["prompts"][0]["text"]
    assert all({"ts", "text"} <= set(p) for t in threads.values() for p in t["prompts"])


def test_build_chain_links_reports_by_transcript_path(project: SimpleNamespace) -> None:
    threads = _threads(chain.build_chain(str(project.worker)))
    gen = threads[GEN]
    assert gen["href"] == followups.report_href(gen["transcript"])


def test_timeline_entries_are_placed_in_the_stage_they_happened_in() -> None:
    """某一刻落在哪个阶段:阶段之前记「开跑前」,阶段之间与最后一段之后记「<前一段> 之后」。"""
    stages = [
        {"label": "Run", "start_ts": "2026-09-21T14:56:00.000Z", "end_ts": "2026-09-21T14:56:21.000Z"},
        {"label": "Spec", "start_ts": "2026-09-21T14:57:00.000Z", "end_ts": "2026-09-21T15:21:00.000Z"},
        {"label": "Retrospect", "start_ts": "2026-09-21T17:21:00.000Z", "end_ts": "2026-09-21T17:34:30.000Z"},
    ]
    local = "-07:00"  # 带本地时区的时刻与 transcript 的 Z 混排
    timeline = [
        {"kind": "error", "ts": f"2026-09-21T07:54:12{local}"},
        {"kind": "decision", "ts": f"2026-09-21T08:05:53{local}"},
        {"kind": "decision", "ts": f"2026-09-21T07:56:40{local}"},
        {"kind": "evaluation", "ts": "2026-09-21T17:26:41+00:00"},
        {"kind": "evaluation", "ts": "2026-09-21T17:34:35+00:00"},
        {"kind": "decision", "ts": ""},
    ]
    placed = [chain.stage_of(e["ts"], stages) for e in timeline]
    assert placed == ["开跑前", "Spec", "Run 之后", "Retrospect", "Retrospect 之后", None]


def test_entries_after_the_trailing_rounds_segment_keep_its_name() -> None:
    """末段已经是「后续轮」时,其后的条目不再叠一个「之后」。"""
    stages = [{"label": "Visual Verify", "start_ts": "2026-09-21T19:00:00Z", "end_ts": "2026-09-21T19:10:00Z"},
              {"label": claude_adapter.TRAILING_ROUNDS_LABEL,
               "start_ts": "2026-09-21T19:20:00Z", "end_ts": "2026-09-21T19:30:00Z"}]
    assert chain.stage_of("2026-09-21T19:31:00Z", stages) == claude_adapter.TRAILING_ROUNDS_LABEL


def test_build_chain_aggregates_totals_entropy_and_findings(project: SimpleNamespace) -> None:
    c = chain.build_chain(str(project.worker))
    assert c["totals"]["threads"] == 7 and c["totals"]["threads_missing"] == 0
    assert c["totals"]["tool_calls"] == 7 and c["totals"]["tool_failed"] == 1
    assert c["started_at"] == "2026-09-19T12:00:00.000Z"
    assert [(r["run_id"], [i["total_H"] for i in r["iterations"]]) for r in c["ecat_runs"]] == [
        (RUN_ID, [0.2521, 0.0422])]
    assert all({"session_id", "thread_id", "role", "level", "rule"} <= set(f) for f in c["findings"])


def test_build_chain_scans_the_ecat_runs_once(project: SimpleNamespace, monkeypatch) -> None:
    """每个 ECAT 会话的 extract 都要 run 上下文;不共享扫描,一条链就是
    会话数 × run 数遍的 run 目录扫描。"""
    calls = {"history": 0, "streams": 0}
    load, streams = ecat._load_history, ecat._stream_sessions

    def counted_load(d):
        calls["history"] += 1
        return load(d)

    def counted_streams(h):
        calls["streams"] += 1
        return streams(h)

    monkeypatch.setattr(ecat, "_load_history", counted_load)
    monkeypatch.setattr(ecat, "_stream_sessions", counted_streams)
    chain.build_chain(str(project.worker))
    assert calls == {"history": 1, "streams": 1}
    ecat.list_runs(str(project.harmony))
    assert calls["history"] == 2, "共享只在一次 build 之内,外面照常现读"


def _get(base: str, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(base + path, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def test_serve_routes_chain_page_and_data(project: SimpleNamespace) -> None:
    srv = serve.make_server("x", port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        ident = urllib.parse.quote(str(project.worker), safe="")
        status, page = _get(base, f"/api/insight1/chain/{ident}")
        assert status == 200 and "会话总览" in page and json.dumps(str(project.worker)) in page
        assert "/api/insight1/chain-data/" in page
        status, body = _get(base, f"/api/insight1/chain-data/{ident}")
        assert status == 200
        data = json.loads(body)
        assert data["anchor"] == W and data["totals"]["threads"] == 7
        # 总览里的报告链接能直接打开(ECAT rollout 不在会话发现的根里也行)
        gen = _threads(data)[GEN]
        status, report = _get(base, gen["href"])
        assert status == 200 and "trace-data" in report
    finally:
        srv.shutdown()
        srv.server_close()
