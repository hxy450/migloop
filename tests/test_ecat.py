"""ECAT 会话适配(移植自 hmigbot-plus tests/web/test_insight1_ecat.py,90b6726d / 739088ca)。

ECAT 的 generator / discriminator 会话是标准 Claude Code transcript,只是落在
``<harmony>/.ecat/agents/<role>/projects/<slug>/<sid>.jsonl``(每个角色一个
CLAUDE_CONFIG_DIR)。本文件钉住:
  · run 聚合:按 <harmony>/.migbot/ecat_runs/run_* 把会话按轮次挂到熵曲线上,
    并数出判官派发形态(entropy-judge vs general-purpose,#161 的症状);
  · trace 标注:meta.ecat 与阶段标签写明角色与轮次;
  · codex 线:按 run 目录 stream 的 init thread id 挂 rollout。
产品侧的会话清单 / 路由 / 项目空间准入不在 migloop,对应用例不搬。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migloop import ecat, service

GEN_SID = "e20b4ce1-b84b-457f-aaa5-1929046c9809"
DISC_SID = "cfad7bf2-1774-45cb-864a-61339fa8a6c0"
GEN1_SID = "a006ac5a-be0a-4146-974a-af4105b1ab8c"
RUN_ID = "run_20260910_144341"


def _ts(minute: int, second: int = 0) -> str:
    return f"2026-09-10T21:{minute:02d}:{second:02d}.000Z"


def _user(ts: str, text: str, sid: str, cwd: str) -> dict:
    return {"type": "user", "timestamp": ts, "cwd": cwd, "sessionId": sid,
            "message": {"content": text}}


def _agent_call(ts: str, mid: str, subagent_type: str, desc: str) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {
        "model": "claude-opus-5", "id": mid, "usage": {"output_tokens": 10},
        "content": [{"type": "tool_use", "id": f"tu-{mid}", "name": "Agent",
                      "input": {"subagent_type": subagent_type, "description": desc,
                                "prompt": "judge"}}]}}


def _text(ts: str, mid: str, text: str) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {
        "model": "claude-opus-5", "id": mid, "stop_reason": "end_turn",
        "usage": {"output_tokens": 5}, "content": [{"type": "text", "text": text}]}}


def _write(path: Path, recs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


@pytest.fixture
def harmony(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """复刻 test20 run 的落盘形态(时间戳与 sid 取自真实 run,内容最小化)。"""
    h = tmp_path_factory.mktemp("h")
    slug = "proj"  # 真实落盘是 slug(cwd);名字不参与角色认定,取短名免撞 Windows MAX_PATH
    gen_dir = h / ".ecat" / "agents" / "generator" / "projects" / slug
    disc_dir = h / ".ecat" / "agents" / "discriminator" / "projects" / slug
    cwd = str(h)

    # iter-0 discriminator:5 个 entropy-judge 派发失败后 5 个 general-purpose 重派(#161)
    recs = [_user(_ts(43, 46), "# Core task\nYou are the Discriminator in the ECAT "
                  "adversarial loop (iteration 0).\nDetecting…", DISC_SID, cwd)]
    dims = ["page_audit", "feature_check", "entry_nav", "source_parity", "hallucination"]
    for i, d in enumerate(dims):
        recs.append(_agent_call(_ts(44, 15 + i), f"ej{i}", "entropy-judge", f"Judge {d} dimension"))
    for i, d in enumerate(dims):
        recs.append(_agent_call(_ts(45, 39 + i), f"gp{i}", "general-purpose", f"Judge {d} dimension"))
    recs.append(_text(_ts(53, 53), "end0", '{"verdicts": {}}'))
    _write(disc_dir / f"{DISC_SID}.jsonl", recs)
    _write(disc_dir / DISC_SID / "subagents" / "agent-a1.jsonl",
           [_user(_ts(45, 40), "judge", "", cwd), _text(_ts(50, 0), "s1", "{}")])

    # iter-0 generator
    _write(gen_dir / f"{GEN_SID}.jsonl", [
        _user(_ts(53, 53), "# Core task\nFix the HarmonyOS repo…\nYou are the Generator "
              "in the ECAT adversarial loop (iteration 0).", GEN_SID, cwd),
        {"type": "assistant", "timestamp": "2026-09-10T22:33:50.000Z", "message": {
            "model": "claude-opus-5", "id": "g-end", "stop_reason": "end_turn",
            "usage": {"output_tokens": 5}, "content": [{"type": "text", "text": "done"}]}},
    ])
    # iter-1 generator(时间戳 22:44:41)
    _write(gen_dir / f"{GEN1_SID}.jsonl", [
        {"type": "user", "timestamp": "2026-09-10T22:44:41.000Z", "cwd": cwd,
         "sessionId": GEN1_SID, "message": {"content": "You are the Generator in the "
                                             "ECAT adversarial loop (iteration 1)."}},
        {"type": "assistant", "timestamp": "2026-09-10T22:55:20.000Z", "message": {
            "model": "claude-opus-5", "id": "g1-end", "stop_reason": "end_turn",
            "usage": {"output_tokens": 5}, "content": [{"type": "text", "text": "done"}]}},
    ])

    runs = h / ".migbot" / "ecat_runs" / RUN_ID
    runs.mkdir(parents=True)
    hist = [
        {"iteration": 0, "total_H": 0.1066, "breakdown": {"placeholder": 1.0},
         "timestamp": "2026-09-10T21:43:45.934884+00:00"},
        {"iteration": 1, "total_H": 0.0916, "breakdown": {"placeholder": 1.0},
         "timestamp": "2026-09-10T22:34:04.000000+00:00"},
        # 终评把最后一轮再记一次(真实 run 里 iter 2 出现两次):按轮次去重取末条
        {"iteration": 1, "total_H": 0.0916, "breakdown": {"placeholder": 1.0},
         "timestamp": "2026-09-10T23:00:00.000000+00:00"},
    ]
    (runs / "entropy_history.jsonl").write_text(
        "\n".join(json.dumps(r) for r in hist) + "\n", encoding="utf-8")
    (runs / "report.md").write_text("# ECAT report\n", encoding="utf-8")
    return h


# ---------- run 聚合 ----------


def test_list_runs_groups_sessions_by_iteration_with_entropy(harmony: Path):
    runs = ecat.list_runs(str(harmony))
    assert [r["run_id"] for r in runs] == [RUN_ID]
    run = runs[0]
    assert run["final_H"] == pytest.approx(0.0916)
    assert run["report"].endswith("report.md")
    assert [it["iteration"] for it in run["iterations"]] == [0, 1]

    it0, it1 = run["iterations"]
    assert it0["total_H"] == pytest.approx(0.1066) and it0["delta_H"] is None
    assert it1["delta_H"] == pytest.approx(-0.0150, abs=1e-4)

    roles0 = [(s["role"], s["session_id"]) for s in it0["sessions"]]
    assert roles0 == [("discriminator", DISC_SID), ("generator", GEN_SID)]
    assert [s["session_id"] for s in it1["sessions"]] == [GEN1_SID]

    disc = it0["sessions"][0]
    assert disc["duration_ms"] == (10 * 60 + 7) * 1000        # 21:43:46 → 21:53:53
    assert disc["subagents"] == 1
    assert disc["judge_dispatch"] == {"entropy-judge": 5, "general-purpose": 5}
    gen = it0["sessions"][1]
    assert gen["duration_ms"] == (39 * 60 + 57) * 1000        # 21:53:53 → 22:33:50
    assert gen["judge_dispatch"] == {}
    assert gen["sid8"] == GEN_SID[:8]


def test_list_runs_without_ecat_dir_is_empty(tmp_path: Path):
    assert ecat.list_runs(str(tmp_path)) == []
    assert ecat.list_runs("") == []


def test_session_meta_reads_role_and_iteration(harmony: Path):
    p = next(harmony.glob(f".ecat/agents/discriminator/projects/*/{DISC_SID}.jsonl"))
    meta = ecat.session_meta(str(p))
    assert (meta["role"], meta["iteration"]) == ("discriminator", 0)
    assert ecat.role_of("/x/y/.claude/projects/a/b.jsonl") is None


# ---------- trace 标注 ----------


def test_extract_trace_marks_ecat_role_and_iteration(harmony: Path):
    p = next(harmony.glob(f".ecat/agents/generator/projects/*/{GEN_SID}.jsonl"))
    trace = service.extract_trace(str(p))
    e = trace["meta"]["ecat"]
    assert (e["role"], e["iteration"], e["run_id"]) == ("generator", 0, RUN_ID)
    assert e["total_H"] == pytest.approx(0.1066) and e["judge_dispatch"] == {}
    assert trace["stages"][0]["label"] == "ECAT Generator · iter 0"


def test_extract_trace_derives_dispatch_from_trace_not_a_rescan(harmony: Path, monkeypatch):
    """正在报告的会话从已解析的 trace 取派发形态,不再整份重扫。"""
    p = next(harmony.glob(f".ecat/agents/discriminator/projects/*/{DISC_SID}.jsonl"))
    monkeypatch.setattr(ecat, "_META_CACHE", {})
    scanned: list[str] = []
    real_scan = ecat._scan_meta
    monkeypatch.setattr(ecat, "_scan_meta", lambda path, role: scanned.append(path) or real_scan(path, role))
    trace = service.extract_trace(str(p))
    assert trace["meta"]["ecat"]["judge_dispatch"] == {"entropy-judge": 5, "general-purpose": 5}
    assert trace["meta"]["ecat"]["run_id"] == RUN_ID
    assert str(p) not in scanned, "当前会话不该再被整份扫描"


def test_non_ecat_session_is_left_alone(tmp_path: Path):
    p = tmp_path / "proj" / "s.jsonl"
    _write(p, [_user(_ts(0), "hi", "s", str(tmp_path)), _text(_ts(1), "m", "ok")])
    trace = service.extract_trace(str(p))
    assert "ecat" not in trace["meta"]


# ---------- codex 线(#311) ----------
#
# codex_sdk 线的角色会话不落 <harmony>/.ecat/agents/<role>/projects/(Codex 不读
# CLAUDE_CONFIG_DIR,rollout 一律落 ~/.codex/sessions/<日期>/rollout-…-<thread>.jsonl),
# 路径里没有角色。runner 把每个角色的事件流 tee 到 <run>/<N>/<role>.stream.jsonl,
# 首行 init 的 session_id 就是 thread id —— 关联靠它,不靠时间窗猜。

CX_GEN_TID = "01a0c5fe-0414-7d90-a009-c210df253cab"
CX_DISC_TID = "01a0c5fd-00e6-77a1-b92a-c0e5e4472d50"
CX_DISC1_TID = "01a0c607-a79d-7331-8432-7e199ac5b3f0"
CX_RUN_ID = "run_20260921_150008"


def _stream(path: Path, tid: str, cwd: str, start: str, end: str) -> None:
    """复刻 runner tee 出的 <role>.stream.jsonl:首行 init,末行 result。"""
    _write(path, [
        {"subtype": "init", "session_id": tid, "model": "glm-5.3", "cwd": cwd, "timestamp": start},
        {"type": "user", "timestamp": start, "message": {"content": [
            {"type": "text", "text": "# Core task\nECAT adversarial loop (iteration ?)"}]}},
        {"type": "result", "session_id": tid, "is_error": False, "timestamp": end},
    ])


def _rollout(sessions: Path, stamp: str, tid: str, cwd: str, parent: str | None = None) -> Path:
    src: dict = {"subagent": {"thread_spawn": {"parent_thread_id": parent}}} if parent else {}
    payload = {"id": tid, "session_id": parent or tid, "cwd": cwd, "cli_version": "0.147.0",
               "timestamp": f"{stamp[:10]}T{stamp[11:].replace('-', ':')}.000Z"}
    if src:
        payload["source"] = src
        payload["thread_source"] = "subagent"
    f = sessions / "2026" / "09" / "21" / f"rollout-{stamp}-{tid}.jsonl"
    _write(f, [
        {"type": "session_meta", "timestamp": payload["timestamp"], "payload": payload},
        {"type": "turn_context", "timestamp": payload["timestamp"], "payload": {"model": "glm-5.3"}},
        {"type": "event_msg", "timestamp": payload["timestamp"],
         "payload": {"type": "user_message", "message": "go"}},
        {"type": "event_msg", "timestamp": payload["timestamp"], "payload": {"type": "task_complete"}},
    ])
    return f


@pytest.fixture
def codex_harmony(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """codex_sdk 线 ECAT 落盘形态:角色目录无 projects/,run 目录带 stream,rollout 在 codex 根。

    iter 0:discriminator + generator;iter 1:新 discriminator + **同一个** generator
    thread(实录:generator 跨轮 resume 同一 thread)。另放一条 cwd 属于别的工程、
    thread id 却被写进 stream 的 rollout,验证准入线。
    """
    from migloop.adapters import codex as codex_adapter

    h = tmp_path / "hmos"
    h.mkdir()
    for role in ("generator", "discriminator"):
        (h / ".ecat" / "agents" / role / "skills").mkdir(parents=True)
    sessions = tmp_path / "codex" / "sessions"
    monkeypatch.setattr(codex_adapter, "default_root", lambda: str(sessions))

    cwd = str(h)
    run = h / ".migbot" / "ecat_runs" / CX_RUN_ID
    _stream(run / "0" / "discriminator.stream.jsonl", CX_DISC_TID, cwd,
            "2026-09-21T22:01:27.000000+00:00", "2026-09-21T22:02:30.000000+00:00")
    _stream(run / "0" / "generator.stream.jsonl", CX_GEN_TID, cwd,
            "2026-09-21T22:02:34.000000+00:00", "2026-09-21T22:08:00.000000+00:00")
    _stream(run / "1" / "discriminator.stream.jsonl", CX_DISC1_TID, cwd,
            "2026-09-21T22:13:05.000000+00:00", "2026-09-21T22:14:40.000000+00:00")
    _stream(run / "1" / "generator.stream.jsonl", CX_GEN_TID, cwd,
            "2026-09-21T22:14:51.000000+00:00", "2026-09-21T22:15:04.000000+00:00")
    hist = [
        {"iteration": 0, "total_H": 0.075, "breakdown": {"placeholder": 1.0},
         "timestamp": "2026-09-21T22:01:27+00:00"},
        {"iteration": 1, "total_H": 0.05, "breakdown": {"placeholder": 1.0},
         "timestamp": "2026-09-21T22:13:05+00:00"},
    ]
    (run / "entropy_history.jsonl").write_text(
        "\n".join(json.dumps(r) for r in hist) + "\n", encoding="utf-8")

    gen = _rollout(sessions, "2026-09-21T15-02-33", CX_GEN_TID, cwd)
    _rollout(sessions, "2026-09-21T15-01-27", CX_DISC_TID, cwd)
    # generator 的并行 worker:子 rollout,由 discover_rollout_tree 并入,不单独挂
    _rollout(sessions, "2026-09-21T15-03-00", "01a0c5ff-0000-7000-8000-000000000001", cwd,
             parent=CX_GEN_TID)
    # 别的工程的 rollout(thread id 与 iter-1 discriminator 撞上):cwd 不是本工程,不收
    _rollout(sessions, "2026-09-21T15-13-05", CX_DISC1_TID, str(tmp_path / "other"))
    return {"harmony": h, "sessions": sessions, "gen": gen}


def test_list_runs_attaches_codex_sessions_by_stream_init(codex_harmony: dict[str, Path]) -> None:
    runs = ecat.list_runs(str(codex_harmony["harmony"]))
    assert [r["run_id"] for r in runs] == [CX_RUN_ID]
    run = runs[0]
    it0 = run["iterations"][0]
    assert [(s["role"], s["iteration"], s["session_id"]) for s in it0["sessions"]] == [
        ("discriminator", 0, CX_DISC_TID), ("generator", 0, CX_GEN_TID)]
    gen = it0["sessions"][1]
    assert gen["transcript"] == str(codex_harmony["gen"])
    assert gen["started_at"].startswith("2026-09-21T22:02:34")
    assert gen["duration_ms"] == (5 * 60 + 26) * 1000     # 22:02:34 → 22:08:00,按本轮 stream 算
    assert gen["subagents"] == 1
    assert gen["judge_dispatch"] == {}
    assert run["unmatched_sessions"] == []


def test_codex_generator_thread_reused_across_iterations(codex_harmony: dict[str, Path]) -> None:
    """generator 跨轮复用同一 thread:一个 rollout 同时挂到 iter 0 与 iter 1,不按会话去重。"""
    run = ecat.list_runs(str(codex_harmony["harmony"]))[0]
    it0, it1 = run["iterations"]
    assert CX_GEN_TID in {s["session_id"] for s in it0["sessions"]}
    assert CX_GEN_TID in {s["session_id"] for s in it1["sessions"]}
    gen1 = next(s for s in it1["sessions"] if s["session_id"] == CX_GEN_TID)
    assert gen1["iteration"] == 1 and gen1["started_at"].startswith("2026-09-21T22:14:51")


def test_codex_rollout_of_other_project_is_not_attached(codex_harmony: dict[str, Path]) -> None:
    """stream 里记了 thread id,但 rollout 的 cwd 是别的工程 —— 准入线不放宽。"""
    run = ecat.list_runs(str(codex_harmony["harmony"]))[0]
    it1 = run["iterations"][1]
    assert [s["role"] for s in it1["sessions"]] == ["generator"]
    assert run["session_count"] == 3          # disc0 + gen(iter0) + gen(iter1)
    assert ecat.role_of(str(next(codex_harmony["sessions"].rglob(f"*{CX_DISC1_TID}.jsonl")))) is None


def test_extract_trace_marks_codex_ecat_session(codex_harmony: dict[str, Path]) -> None:
    gen = str(codex_harmony["gen"])
    assert ecat.role_of(gen) == "generator"
    trace = service.extract_trace(gen)
    e = trace["meta"]["ecat"]
    assert (e["role"], e["iteration"], e["run_id"]) == ("generator", 0, CX_RUN_ID)
    assert e["iterations"] == [0, 1]
    assert e["total_H"] == pytest.approx(0.075)
    assert trace["stages"][0]["label"] == "ECAT Generator · iter 0"
