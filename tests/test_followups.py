"""执行拓扑的后续节点:主会话之后、同一鸿蒙工程里跑起来的能力会话(DT 等)与 ECAT run。

移植自 hmigbot-plus tests/web/test_insight1_followups.py(fe468482)。

它们各自是独立 transcript,主会话的 transcript 里没有一条记录提到它们,拓扑
只画本会话的阶段与子代理,于是「执行拓扑看不到 DT 和 ECAT」(2026-09-11 用户
实测)。报告 trace 按会话自己的信息补:同 transcript 目录里开工晚于本会话
结束、且有工具调用的会话(纯对话的托管审查不算);``<harmony>/.migbot/ecat_runs``
里开跑晚于本会话开始的 run。不按能力名识别。migloop 里补在 service.report_trace。
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

from migloop import ecat as ecat_mod
from migloop import followups, service
from migloop.render import build_html

MAIN = "300a88bb-0f60-4119-aae7-82c87318c3b3"
DT = "012f584d-9fc8-4272-805f-d431f51ed758"
REVIEW = "bc380a64-4a4a-44d3-9966-c37768f18645"
EARLY = "11111111-0000-0000-0000-000000000000"
DISC = "4861fbae-a5e4-414f-b5c3-c443f22f3512"


def _ts(hour: int, minute: int = 0) -> str:
    return f"2026-09-10T{hour:02d}:{minute:02d}:00.000Z"


def _user(ts: str, text: str, cwd: str, sid: str) -> dict:
    return {"type": "user", "timestamp": ts, "cwd": cwd, "sessionId": sid,
            "message": {"content": text}}


def _tool(ts: str, mid: str, name: str, inp: dict, attribution: str | None = None) -> dict:
    rec = {"type": "assistant", "timestamp": ts, "message": {
        "model": "claude-opus-5", "id": mid, "usage": {"output_tokens": 10},
        "content": [{"type": "tool_use", "id": f"tu-{mid}", "name": name, "input": inp}]}}
    if attribution:
        rec["attributionSkill"] = attribution
    return rec


def _text(ts: str, mid: str, text: str) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {
        "model": "claude-opus-5", "id": mid, "stop_reason": "end_turn",
        "usage": {"output_tokens": 5}, "content": [{"type": "text", "text": text}]}}


def _write(path: Path, recs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


def _report(path: Path, *, static: bool = False) -> dict:
    return service.report_trace(str(path), static=static)


@pytest.fixture
def project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """复刻 test20:主会话 12:00-13:00;ECAT run 13:05 起两轮;DT 14:00-15:00
    (有 Bash + Agent,归属戳 arkts-dt-verifier);托管审查 14:10 纯对话;
    另有一条 10:00 的早会话。"""
    tmp_path = tmp_path_factory.mktemp("h")
    harmony = tmp_path / "harmony"
    cwd = str(harmony)
    slug = "proj"  # 真实落盘是 slug(cwd);同目录 = 同工程,名字本身不参与判断
    proj = tmp_path / "cc" / "projects" / slug
    _write(proj / f"{MAIN}.jsonl", [
        _user(_ts(12), "/a2h-run", cwd, MAIN),
        _tool(_ts(12, 30), "m1", "Bash", {"command": "ls"}, "a2h-execute"),
        _text(_ts(13), "m2", "done")])
    _write(proj / f"{DT}.jsonl", [
        _user(_ts(14), "调用 arkts-dt-verifier skill", cwd, DT),
        _tool(_ts(14, 10), "d1", "Bash", {"command": "hvigorw"}, "arkts-dt-verifier"),
        _tool(_ts(14, 20), "d2", "Agent", {"subagent_type": "general-purpose",
                                            "description": "Step 1", "prompt": "…"},
              "arkts-dt-verifier"),
        _text(_ts(15), "d3", "报告已写出")])
    # 托管审查会验盘:只有 Glob/Read 之类只读调用(test20 的 6a54ef85 实测 9 次 Glob)
    _write(proj / f"{REVIEW}.jsonl", [
        _user(_ts(14, 10), "你可以使用 Glob / Read 核实工作目录下的产物文件", cwd, REVIEW),
        _tool(_ts(14, 10), "r0", "Glob", {"pattern": "docs/*.md"}),
        _tool(_ts(14, 10), "r2", "Read", {"file_path": "docs/x.md"}),
        _text(_ts(14, 11), "r1", '{"decision": "let_exit"}')])
    _write(proj / f"{EARLY}.jsonl", [
        _user(_ts(10), "早一轮", cwd, EARLY),
        _tool(_ts(10, 5), "e1", "Bash", {"command": "ls"}),
        _text(_ts(10, 10), "e2", "ok")])

    runs = harmony / ".migbot" / "ecat_runs" / "run_20260910_130500"
    runs.mkdir(parents=True)
    (runs / "entropy_history.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"iteration": 0, "total_H": 0.5, "breakdown": {}, "timestamp": _ts(13, 5)},
        {"iteration": 1, "total_H": 0.3, "breakdown": {}, "timestamp": _ts(13, 30)},
    ]) + "\n", encoding="utf-8")
    disc_dir = harmony / ".ecat" / "agents" / "discriminator" / "projects" / slug
    _write(disc_dir / f"{DISC}.jsonl", [
        _user(_ts(13, 31), "You are the Discriminator in the ECAT adversarial loop "
              "(iteration 1).", cwd, DISC),
        _tool(_ts(13, 32), "j1", "Agent", {"subagent_type": "entropy-judge",
                                            "description": "Judge page_audit dimension",
                                            "prompt": "…"}),
        _text(_ts(13, 40), "j2", "{}")])
    return proj / f"{MAIN}.jsonl", disc_dir / f"{DISC}.jsonl"


def test_main_session_gets_followups_in_time_order(project: tuple[Path, Path]) -> None:
    main, disc = project
    fups = _report(main)["followups"]
    assert [(f["kind"], f["label"]) for f in fups] == [
        ("ecat", "ECAT 精修 · 2 轮"), ("session", "arkts-dt-verifier")]
    ecat, dt = fups
    assert ecat["run_id"] == "run_20260910_130500"
    assert ecat["sub"].startswith("H 0.500 → 0.300")
    # --serve 按 transcript 路径寻址:ECAT 会话不在会话发现的根里,按会话号找不到
    assert ecat["start_ts"].startswith("2026-09-10T13:05") and ecat["href"] == followups.report_href(str(disc))
    assert dt["sid"] == DT and dt["href"] == followups.report_href(str(main.parent / f"{DT}.jsonl"))
    assert urllib.parse.unquote(dt["href"].rsplit("/", 1)[1]) == str(main.parent / f"{DT}.jsonl")
    assert dt["tool_calls"] == 2 and dt["agent_count"] == 1
    assert ecat_mod._parse_ts(dt["start_ts"]) == ecat_mod._parse_ts(_ts(14))
    assert dt["duration_ms"] == 3_600_000
    assert all(f["id"] == f"f{i}" for i, f in enumerate(fups))


def test_static_report_draws_followups_without_links(project: tuple[Path, Path]) -> None:
    """导出的自包含 HTML 没有服务端:节点照画,不给跳转地址。"""
    main, _ = project
    fups = _report(main, static=True)["followups"]
    assert len(fups) == 2 and all(f["href"] is None for f in fups)


def test_ecat_session_and_orphans_carry_no_followups(
    tmp_path: Path, project: tuple[Path, Path],
) -> None:
    """ECAT 角色会话不是主链,不挂后续;找不到工程目录/没有后续时给空表而不是缺键。"""
    _, disc = project
    assert _report(disc).get("followups", []) == []
    lone = tmp_path / "cc" / "projects" / "-x" / "aaaaaaaa-0000-0000-0000-000000000000.jsonl"
    _write(lone, [_user(_ts(1), "hi", str(tmp_path / "nowhere"), "aaaaaaaa"),
                  _text(_ts(1, 1), "x", "ok")])
    assert _report(lone)["followups"] == []


def test_later_session_scan_is_remembered(project: tuple[Path, Path], monkeypatch) -> None:
    """后继会话的单趟扫描按 (mtime, size) 记住:第二次出报告不再重读。"""
    main, _ = project
    monkeypatch.setattr(followups, "_SCAN_CACHE", {})
    opened: list[str] = []

    def spy(path, *a, **kw):
        opened.append(str(path))
        return open(path, *a, **kw)

    monkeypatch.setattr(followups, "open", spy, raising=False)   # 只截 followups 自己的整份扫描
    trace = service.extract_trace(str(main))
    first = followups.collect(str(main), trace)
    assert [p for p in opened if p.endswith(f"{DT}.jsonl")], "第一次要扫后继会话"
    opened.clear()
    assert followups.collect(str(main), trace) == first
    assert opened == []


def test_report_html_embeds_followups(project: tuple[Path, Path]) -> None:
    main, _ = project
    html = build_html(_report(main))
    assert '"followups":[{' in html and "ECAT 精修 · 2 轮" in html
    # 模板要真的画:后续节点走 D.followups
    assert "D.followups" in html
