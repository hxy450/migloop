"""Codex 增量监控 —— 传输层语义 + 记录归约 + 子代理树的增量发现(移植自 hmigbot-plus tests/plus/unit/test_insight1_codexlive.py)。

传输层(TranscriptStream)是 live/monitor.py 流机制的重写而非搬动,
两份实现的语义必须一致 —— 半行留存、无换行收尾、截断重放,这里逐条钉住。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from migloop.live.codexlive import CodexLiveMonitor
from migloop.live.livestream import TranscriptStream

# ---------- 合成 rollout ----------


def _rec(rtype: str, payload: dict[str, Any], ts: str = "2026-08-18T10:00:00Z") -> str:
    return json.dumps({"timestamp": ts, "type": rtype, "payload": payload}) + "\n"


def _meta(tid: str, session: str, parent: str | None = None, nick: str | None = None) -> str:
    p: dict[str, Any] = {"id": tid, "session_id": session}
    if parent:
        p["source"] = {"subagent": {"thread_spawn": {
            "parent_thread_id": parent, "agent_nickname": nick or tid}}}
    return _rec("session_meta", p)


def _call(cid: str, name: str = "shell") -> str:
    return _rec("response_item", {"type": "function_call", "call_id": cid,
                                  "name": name, "arguments": "{}"})


def _out(cid: str, exit_code: int = 0) -> str:
    return _rec("response_item", {"type": "function_call_output", "call_id": cid,
                                  "output": f"Exit code: {exit_code}\nOutput:\nok"})


def _tokens(n: int) -> str:
    return _rec("event_msg", {"type": "token_count",
                              "info": {"total_token_usage": {"output_tokens": n}}})


def _life(kind: str) -> str:
    return _rec("event_msg", {"type": kind})


def _root(tmp: Path, tid: str = "t-root", session: str = "s-1") -> Path:
    day = tmp / "sessions" / "2026" / "08" / "18"
    day.mkdir(parents=True, exist_ok=True)
    f = day / f"rollout-2026-08-18T10-00-00-{tid}.jsonl"
    f.write_text(_meta(tid, session) + _life("task_started"), encoding="utf-8")
    return f


# ---------- 传输层 ----------


def test_stream_reads_only_appended_bytes(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text('{"a":1}\n', encoding="utf-8")
    st = TranscriptStream(path=str(f))
    recs, n1, reset = st.read_new()
    assert [r["a"] for r in recs] == [1] and not reset

    with open(f, "a", encoding="utf-8") as fh:
        fh.write('{"a":2}\n')
    recs, n2, _ = st.read_new()
    assert [r["a"] for r in recs] == [2], "第二轮只该看到新增那条"
    assert n2 < n1 + 8


def test_stream_retains_half_line_until_completed(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text('{"a":1}\n{"a":', encoding="utf-8")  # 第二条只写了一半
    st = TranscriptStream(path=str(f))
    recs, _, _ = st.read_new()
    assert [r["a"] for r in recs] == [1]
    assert st.pending_b64, "半行必须留存"

    with open(f, "a", encoding="utf-8") as fh:
        fh.write("2}\n")
    recs, _, _ = st.read_new()
    assert [r["a"] for r in recs] == [2], "拼回后应恰好是完整的第二条"


def test_stream_consumes_final_line_without_newline(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text('{"a":1}', encoding="utf-8")  # 收尾无换行
    st = TranscriptStream(path=str(f))
    recs, _, _ = st.read_new()
    assert [r["a"] for r in recs] == [1]
    assert not st.pending_b64


def test_stream_detects_truncation(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text('{"a":1}\n' * 20, encoding="utf-8")
    st = TranscriptStream(path=str(f))
    st.read_new()
    f.write_text('{"b":1}\n', encoding="utf-8")  # 截断 + 内容替换
    _, _, reset = st.read_new()
    assert reset, "size < offset 必须上报重放"


def test_stream_checkpoint_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text('{"a":1}\n', encoding="utf-8")
    st = TranscriptStream(path=str(f))
    st.read_new()
    st.meta["tool_uses"] = 3
    restored = TranscriptStream.from_json(st.to_json())
    assert restored.offset == st.offset
    assert restored.meta["tool_uses"] == 3
    with open(f, "a", encoding="utf-8") as fh:
        fh.write('{"a":2}\n')
    recs, _, _ = restored.read_new()
    assert [r["a"] for r in recs] == [2], "还原后应从游标处续读，不重放"


# ---------- 归约 ----------


def test_reducer_counts_tools_failures_and_tokens(tmp_path: Path) -> None:
    f = _root(tmp_path)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(_call("c1") + _out("c1", 0) + _call("c2") + _out("c2", 1)
                 + _tokens(500) + _tokens(1200) + _life("task_complete"))
    mon = CodexLiveMonitor(str(f), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    snap = mon.snapshot()
    assert snap["tool_calls"] == 2
    assert snap["tool_failures"] == 1, "Exit code: 1 应计为失败"
    assert snap["output_tokens"] == 1200, "token_count 是累计值,取最新而非求和"
    assert snap["status"] == "waiting", "task_complete 后回到等待"


def test_running_status_follows_lifecycle(tmp_path: Path) -> None:
    f = _root(tmp_path)  # 只有 task_started
    mon = CodexLiveMonitor(str(f), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    assert mon.snapshot()["status"] == "running"


# ---------- 子代理树 ----------


def test_bootstrap_picks_up_existing_subagents(tmp_path: Path) -> None:
    root = _root(tmp_path)
    day = root.parent
    child = day / "rollout-2026-08-18T10-01-00-t-child.jsonl"
    child.write_text(_meta("t-child", "s-1", parent="t-root", nick="conv-1")
                     + _life("task_started") + _call("x1"), encoding="utf-8")
    stranger = day / "rollout-2026-08-18T10-02-00-t-other.jsonl"
    stranger.write_text(_meta("t-other", "s-OTHER"), encoding="utf-8")

    mon = CodexLiveMonitor(str(root), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    snap = mon.snapshot()
    assert [a["desc"] for a in snap["agents"]] == ["conv-1"]
    assert snap["agent_counts"]["running"] == 1


def test_new_subagent_discovered_incrementally(tmp_path: Path) -> None:
    root = _root(tmp_path)
    mon = CodexLiveMonitor(str(root), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    assert mon.snapshot()["agents"] == []

    # 监控开始之后才出生的子代理 —— 增量扫描要靠 mtime 水位线抓到它
    child = root.parent / "rollout-2026-08-18T10-05-00-t-late.jsonl"
    child.write_text(_meta("t-late", "s-1", parent="t-root", nick="late-1")
                     + _life("task_started"), encoding="utf-8")
    mon.poll_once()
    assert [a["desc"] for a in mon.snapshot()["agents"]] == ["late-1"]


def test_unrelated_rollout_lands_in_negative_cache(tmp_path: Path) -> None:
    root = _root(tmp_path)
    mon = CodexLiveMonitor(str(root), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    stranger = root.parent / "rollout-2026-08-18T10-06-00-t-x.jsonl"
    stranger.write_text(_meta("t-x", "s-OTHER"), encoding="utf-8")
    mon.poll_once()
    assert str(stranger) in mon.negative, "确认过不属于这棵树的文件不该反复读首行"


def test_checkpoint_resumes_without_replay(tmp_path: Path) -> None:
    f = _root(tmp_path)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(_call("c1") + _out("c1"))
    cache = str(tmp_path / "cache")
    mon = CodexLiveMonitor(str(f), cache_dir=cache, poll_interval=999)
    mon.poll_once()
    mon.save_checkpoint()
    v1, bytes1 = mon.state["version"], mon.state["bytes_read_total"]

    with open(f, "a", encoding="utf-8") as fh:
        fh.write(_call("c2") + _out("c2"))
    mon2 = CodexLiveMonitor(str(f), cache_dir=cache, poll_interval=999)
    mon2.poll_once()
    assert mon2.state["tool_calls"] == 2, "计数从 checkpoint 续,不归零"
    assert mon2.state["bytes_read_total"] > bytes1
    assert mon2.state["bytes_read_last"] < bytes1, "重启后只读了新增段,没有全量重放"
    assert mon2.state["version"] > v1


# ---------- 重放验证揪出来的三个缺陷(真实 rollout 树,209 工具调用/12 子代理) ----------


def test_child_arriving_before_root_identity_is_not_blacklisted(tmp_path: Path) -> None:
    """root 的 session_meta 还没读进来之前,任何文件都不得进负缓存。

    重放实测:bootstrap 从空文件起步时 root 身份未确认,同会话的 7/12 个
    子代理在 poll 1 被误判「别的会话」判了死刑,后面永远接不回来。
    """
    day = tmp_path / "sessions" / "2026" / "08" / "18"
    day.mkdir(parents=True)
    root = day / "rollout-2026-08-18T10-00-00-t-root.jsonl"
    root.write_text("", encoding="utf-8")  # 关键:root 还是空的,身份未确认
    child = day / "rollout-2026-08-18T10-01-00-t-child.jsonl"
    child.write_text(_meta("t-child", "s-1", parent="t-root", nick="early"),
                     encoding="utf-8")

    mon = CodexLiveMonitor(str(root), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    assert str(child) not in mon.negative, "root 未确认前不能拉黑任何人"

    root.write_text(_meta("t-root", "s-1") + _life("task_started"), encoding="utf-8")
    mon.poll_once()
    mon.poll_once()  # 父注册后下一轮孩子应接上
    assert [a["desc"] for a in mon.snapshot()["agents"]] == ["early"]


def test_second_session_meta_does_not_overwrite_identity(tmp_path: Path) -> None:
    """身份以第一条 session_meta 为准。

    子代理 rollout 会在后面再嵌一条 root 的 session_meta(实测 Lovelace),
    后到覆盖会让 12 个 agent 的 thread_id 塌成 3 个。
    """
    root = _root(tmp_path)
    child = root.parent / "rollout-2026-08-18T10-01-00-t-child.jsonl"
    child.write_text(
        _meta("t-child", "s-1", parent="t-root", nick="c1")
        + _meta("t-root", "s-1")  # 嵌进来的 root 身份副本
        + _call("x1"),
        encoding="utf-8",
    )
    mon = CodexLiveMonitor(str(root), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    agent = mon.snapshot()["agents"][0]
    assert agent["agent_id"] == "t-child", "第二条 session_meta 不得覆盖身份"


def test_session_id_extracted_from_rollout_filename(tmp_path: Path) -> None:
    """Codex 文件名带 rollout-<时间戳>- 前缀,session_id 必须是尾部 uuid。

    拿整个 stem 当身份,会在 root 的 session_meta 读进来之前污染
    「同 session」判定的回落值。
    """
    day = tmp_path / "sessions" / "2026" / "08" / "18"
    day.mkdir(parents=True)
    uid = "01a0048b-be91-7c71-a33f-ee3f6fc061cc"
    f = day / f"rollout-2026-08-15T04-31-02-{uid}.jsonl"
    f.write_text(_meta(uid, uid), encoding="utf-8")
    mon = CodexLiveMonitor(str(f), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    assert mon.state["session_id"] == uid


# ---------- 接到 migloop 的 live 框架 ----------


def test_custom_tool_calls_count_as_tool_calls(tmp_path: Path) -> None:
    """apply_patch 走 custom_tool_call,与 function_call 一样算一次调用。"""
    f = _root(tmp_path)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(_rec("response_item", {"type": "custom_tool_call", "call_id": "p1",
                                        "name": "apply_patch", "input": "*** Begin Patch"}))
        fh.write(_rec("response_item", {"type": "custom_tool_call_output", "call_id": "p1",
                                        "output": "Exit code: 0"}))
    mon = CodexLiveMonitor(str(f), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    assert mon.snapshot()["tool_calls"] == 1


def test_reset_cache_replays_from_the_start(tmp_path: Path) -> None:
    f = _root(tmp_path)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(_call("c1") + _out("c1"))
    cache = str(tmp_path / "cache")
    mon = CodexLiveMonitor(str(f), cache_dir=cache, poll_interval=999)
    mon.poll_once()
    mon.save_checkpoint()
    again = CodexLiveMonitor(str(f), cache_dir=cache, poll_interval=999, reset_cache=True)
    again.poll_once()
    assert again.state["tool_calls"] == 1, "忽略 checkpoint 从头重放,不叠加"


def test_live_http_server_serves_codex_state(tmp_path: Path) -> None:
    """run_live 的 HTTP 层与 CC 共用:/api/state 吃 CodexLiveMonitor 的快照。"""
    import threading
    import urllib.request

    from migloop.adapters import codex
    from migloop.live.monitor import LiveHTTPServer

    assert codex.SUPPORTS_LIVE
    f = _root(tmp_path)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(_call("c1") + _out("c1", 1))
    mon = CodexLiveMonitor(str(f), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    srv = LiveHTTPServer(("127.0.0.1", 0), mon, lambda: b"<html><body>report</body></html>", 1000)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        with urllib.request.urlopen(base + "/api/state", timeout=30) as r:
            state = json.loads(r.read().decode("utf-8"))
        assert state["session_format"] == "codex"
        assert (state["tool_calls"], state["tool_failures"]) == (1, 1)
        with urllib.request.urlopen(base + "/status.html", timeout=30) as r:
            assert r.status == 200
    finally:
        srv.shutdown()
        srv.server_close()


def test_live_stages_follow_the_offline_rules(tmp_path: Path) -> None:
    """codexlive 与离线同一套阶段口径:点 skill 是信号(不足 90 秒不进入)、mark 回执确认后收尾、
    管线收尾后的首条人工输入开后续轮;heartbeat 记程序下发。"""
    def user(text: str, ts: str) -> str:
        return _rec("response_item", {"type": "message", "role": "user",
                                      "content": [{"type": "input_text", "text": text}]}, ts)

    def call(cid: str, cmd: str, ts: str) -> str:
        return _rec("response_item", {"type": "function_call", "call_id": cid, "name": "exec_command",
                                      "arguments": json.dumps({"cmd": cmd})}, ts)

    def out(cid: str, ts: str, code: int = 0) -> str:
        return _rec("response_item", {"type": "function_call_output", "call_id": cid,
                                      "output": f"Process exited with code {code}\nOutput:\n"}, ts)

    f = _root(tmp_path)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(user("[$a2h-spec](/w/.agents/skills/a2h-spec/SKILL.md)", "2026-08-18T10:00:10Z")
                 + _tokens(1).replace("10:00:00", "10:03:00"))
    mon = CodexLiveMonitor(str(f), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    assert mon.snapshot()["current_stage"] == "a2h-spec"
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(call("m1", ".migbot/bin/a2h mark-stage a2h-plan", "2026-08-18T10:20:00Z")
                 + out("m1", "2026-08-18T10:20:01Z", code=1)                      # 没跑成
                 + call("m2", ".migbot/bin/a2h mark-stage a2h-execute", "2026-08-18T10:30:00Z")
                 + out("m2", "2026-08-18T10:30:01Z")
                 + user("<heartbeat><automation_id>x</automation_id>", "2026-08-18T10:40:00Z"))
    mon.poll_once()
    snap = mon.snapshot()
    assert (snap["current_stage"], snap["marked_stages"]) == ("after-pipeline", ["a2h-execute"])
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(user("统计一下用量", "2026-08-18T10:50:00Z"))
    mon.poll_once()
    snap = mon.snapshot()
    assert snap["current_stage"] == "follow-up"
    assert (snap["user_prompts"], snap["program_prompts"]) == (2, 1)


def test_tool_counts_follow_offline_and_skip_the_fork_prefix(tmp_path: Path) -> None:
    """工具数按里层算、主会话与子会话分开;fork 子会话以自己线程 id 的 thread_settings_applied
    为界,之前抄来的父会话前缀不算(离线与 live 同口径)。"""
    from migloop.adapters import codex

    def code_call(cid: str, code: str) -> str:
        return _rec("response_item", {"type": "custom_tool_call", "call_id": cid, "name": "exec", "input": code})

    root = _root(tmp_path)
    with open(root, "a", encoding="utf-8") as fh:
        fh.write(code_call("r1", 'for (const x of ["a","b"]) await tools.exec_command({cmd:"ls"});') + _out("r1"))
    child = root.parent / "rollout-2026-08-18T10-01-00-t-child.jsonl"
    child.write_text(
        _meta("t-child", "s-1", parent="t-root") + _meta("t-root", "s-1")
        + code_call("p1", 'await tools.exec_command({cmd:"prefix"})') + _out("p1")          # 抄来的父会话前缀
        + _rec("event_msg", {"type": "thread_settings_applied", "thread_id": "t-child"})
        + _call("c1") + _out("c1") + _call("c2") + _out("c2"), encoding="utf-8")
    mon = CodexLiveMonitor(str(root), cache_dir=str(tmp_path / "cache"), poll_interval=999)
    mon.poll_once()
    snap = mon.snapshot()
    assert (snap["tool_calls"], snap["subagent_tool_calls"], snap["tool_calls_outer"]) == (2, 2, 1)
    trace = codex.extract(str(root), sessions_root=str(tmp_path / "sessions"))
    assert (trace["totals"]["tool_calls"], trace["totals"]["subagent_tool_calls"]) == (2, 2)
