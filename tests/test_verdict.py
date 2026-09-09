"""结构化结论(verdict):模型输出的 YAML/JSON 块 → 严格解析 → 节点 / 证据 / 边核回账本 → 页面按 缺陷 × 节点 × 版本 着色。

契约(交接说明 2026-09-08 四之 1–7):
- 修复锚点 / 因果角色 / 核验状态三者分开:repair.after 不染红;角色只有 正常 / 带病传递 / 进入·错 / 进入·缺 / 无法确认。
- 标注键 = (缺陷, 节点种类, 节点身份, 版本):共享节点在 A 下正常、B 下进入错,两条记录都保留,不合并。
- 节点坐标显式解析并校验版本范围;主语无效时不拿证据里的节点顶替。
- 模型主张与检查结果独立:引用无效只标出来,不吞;边按账本的写 / 读 / 派发核,相邻 ≠ 事实边。
- 步骤层独立于结论层:失败调用、只查索引、看正文分开记。
- 账本身份不一致告警,历史报告仍可读;旧散文报告标 legacy。
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest

from migloop import atoms, probe, verdict
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call, _rec


def _pool(tmp_path: Any) -> atoms.Ledger:
    """主会话派发 conv-a(读 spec@v1 → 写 A.ets v1)与 fixer(读 A.ets@v1 → 写 v2)。"""
    conv = [_rec("2026-01-01T00:00:00Z", "user", "转换 A"),
            *_read_call("2026-01-01T00:00:10Z", "c1", "/proj/spec/pages/A.md", "spec\n"),
            *_call("2026-01-01T00:00:20Z", "c2", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets")]
    fix = [_rec("2026-01-01T02:00:00Z", "user", "修 A"),
           *_read_call("2026-01-01T02:00:10Z", "f1", "/proj/entry/A.ets", "a\n"),
           *_call("2026-01-01T02:00:20Z", "f2", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-a", "prompt": "转换 A"}, "done",
                   toolUseResult={"agentId": "c"}),
            *_call("2026-01-01T02:00:00Z", "m2", "Agent", {"name": "fixer", "prompt": "修 A"}, "done",
                   toolUseResult={"agentId": "f"})]
    return _ledger(tmp_path, main, {"agent-c": conv, "agent-f": fix})


def _run_dir(tmp_path: Any, seq: list[dict[str, Any]], report: str,
             verdict_json: dict[str, Any] | None = None, name: str = "lab") -> str:
    d = tmp_path / "runs" / name / "chain10-A.ets" / "rep1"
    os.makedirs(d, exist_ok=True)
    with open(d / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump({"cost_usd": 1.5, "num_turns": 9, "transcript": {"seq": seq}}, fh)
    with open(d / "result.json", "w", encoding="utf-8") as fh:
        json.dump({"result": report}, fh)
    if verdict_json is not None:
        with open(d / "verdict.json", "w", encoding="utf-8") as fh:
            json.dump(verdict_json, fh, ensure_ascii=False)
    return str(d)


def _seq_of(led: atoms.Ledger, aid: str, tool: str) -> int:
    return next(a.seq for a in led.agents[aid].actions if a.tool == tool)


def _ref(led: atoms.Ledger, seq: int) -> str:
    from migloop import atoms_text
    return atoms_text._core(seq, led.locs[seq])


def _block(body: str) -> str:
    return "散文报告在前。\n\n```yaml\n" + body + "```\n"


def _build(led: atoms.Ledger, data: dict[str, Any]) -> dict[str, Any]:
    return verdict.build(led, {**data, "ledger": atoms.ledger_identity(led)}, [], {})


# ═══════════════ 解析:严格 schema,重复键与无效类型拒绝 ═══════════════

def test_extract_and_parse_reject_bad_blocks() -> None:
    assert verdict.extract_block("没有围栏块") is None
    assert verdict.extract_block("```yaml\nfoo: 1\n```") is None            # 不是结论块
    kind, raw = verdict.extract_block("```json\n{\"schema\": \"migloop-verdict/1\", \"defects\": []}\n```") or ("", "")
    assert kind == "json" and raw.startswith("{")
    # JSON 重复键
    data, errs = verdict.parse_block("json", '{"schema": "migloop-verdict/1", "defects": [], "defects": []}')
    assert data is None and any("重复键" in e for e in errs)
    # 顶层未知键 / schema 不对 / 角色不在词表 / 节点不是字符串 / 缺 reason
    bad = {"schema": "migloop-verdict/0", "foo": 1,
           "defects": [{"id": "A", "title": "t", "nodes": [{"node": 3, "role": "错"}]}]}
    errs = verdict.validate(bad)
    joined = "\n".join(errs)
    assert "schema" in joined and "foo" in joined and "role" in joined and "node" in joined and "reason" in joined
    # 合法的最小块零错误
    good = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t", "nodes": [
        {"node": "file:entry/A.ets@v1", "role": "带病传递", "reason": "r"}]}]}
    assert verdict.validate(good) == []
    # 缺陷 id 重复
    dup = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t", "nodes": []}, {"id": "A", "title": "u", "nodes": []}]}
    assert any("重复" in e for e in verdict.validate(dup))
    # 边的关系词表、checks 的结果词表
    e2 = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t", "nodes": [],
                                                  "edges": [{"from": "file:a@v1", "to": "agent:b@v1", "relation": "继承"}]}]}
    assert any("relation" in e for e in verdict.validate(e2))
    c2 = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t", "nodes": [
        {"node": "file:a@v1", "role": "正常", "reason": "r", "checks": [{"claim": "x", "result": "maybe"}]}]}]}
    assert any("result" in e for e in verdict.validate(c2))


def test_yaml_duplicate_keys_rejected() -> None:
    pytest.importorskip("yaml")
    data, errs = verdict.parse_block("yaml", "schema: migloop-verdict/1\ndefects: []\ndefects: []\n")
    assert data is None and any("重复键" in e for e in errs)
    data, errs = verdict.parse_block("yaml", "schema: migloop-verdict/1\ndefects: []\n")
    assert errs == [] and data["schema"] == verdict.SCHEMA
    # 无法解析的 YAML 保留原文与错误,不猜
    data, errs = verdict.parse_block("yaml", "schema: [unclosed\n")
    assert data is None and errs


@pytest.mark.parametrize("tail", ["1: x\n", "? [x, y]\n: z\n", "notes: &cycle [*cycle]\n",
                                 "notes: !!python/object/apply:os.system ['echo invalid']\n"])
def test_unsafe_or_non_string_yaml_keys_are_diagnostic(tail: str) -> None:
    pytest.importorskip("yaml")
    raw = "schema: migloop-verdict/1\ndefects: []\n" + tail
    loaded = verdict.load_block(_block(raw))
    assert loaded["found"] and loaded["data"] is None and loaded["errors"]
    assert loaded["raw"] == raw


def test_parser_limits_nesting_size_and_schema_keys() -> None:
    pytest.importorskip("yaml")
    for kind, raw in (("yaml", "x: " + "[" * 80 + "0" + "]" * 80),
                      ("json", "[" * 2000 + "0" + "]" * 2000),
                      ("json", " " * (verdict._MAX_BLOCK_CHARS + 1))):
        data, errors = verdict.parse_block(kind, raw)
        assert data is None and errors
    assert verdict.validate({"schema": verdict.SCHEMA, "defects": [], 1: "x"})
    nested: Any = []
    nested.append(nested)
    assert verdict.validate({"schema": verdict.SCHEMA, "defects": nested})


@pytest.mark.parametrize("spec", ["file:entry/A.ets", "agent:conv-a"])
def test_schema_requires_node_versions(spec: str) -> None:
    data = {"schema": verdict.SCHEMA, "root": spec, "defects": [{"id": "A", "title": "t",
            "repair": {"before": spec, "after": spec}, "entry": [spec],
            "nodes": [{"node": spec, "role": "正常", "reason": "r"}],
            "edges": [{"from": spec, "to": spec}]}]}
    errors = verdict.validate(data)
    assert len(errors) == 7 and all("缺版本号" in e for e in errors)


def test_load_block_and_repair_prompt() -> None:
    lb = verdict.load_block("只有散文")
    assert lb["found"] is False and lb["data"] is None
    lb = verdict.load_block(_block("schema: migloop-verdict/1\ndefects: []\n"))
    assert lb["found"] and lb["errors"] == [] and lb["data"]["defects"] == []
    lb = verdict.load_block(_block("schema: migloop-verdict/1\ndefects: [{id: A}]\n"))
    assert lb["found"] and lb["errors"]
    rp = verdict.repair_prompt(lb)
    assert "migloop-verdict/1" in rp and lb["errors"][0] in rp and "不要再调用工具" in rp


# ═══════════════ 节点坐标:显式解析 + 版本范围 ═══════════════

def test_nodes_resolve_with_version_range_and_invalid_subjects_stay_invalid(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    ok = verdict.resolve_node(led, "file:entry/A.ets@v1")
    assert ok["ok"] and ok["key"] == "/proj/entry/A.ets" and ok["v"] == 1 and ok["kind"] == "file"
    assert verdict.resolve_node(led, "agent:conv-a@v1")["key"] == "agent-c"          # 名字 → 账本 id
    assert verdict.resolve_node(led, "agent:agent-c@v1")["ok"]
    main = verdict.resolve_node(led, f"agent:{MAIN_ID}@v2")                            # 主会话 __main__:<sid8>
    assert main["ok"] and main["key"] == MAIN_ID and main["v"] == 2
    assert verdict.resolve_node(led, "agent:__main__:abcd@v1")["key"] == MAIN_ID       # 会话号前缀,唯一才认
    for spec, word in (("file:nope.ets@v1", "不在账本"), ("agent:agent-c@v0", "越界"), ("file:entry/A.ets@v9", "越界"),
                       ("agent:agent-c@v3", "越界"), ("file:entry/A.ets", "缺版本号"), ("A.ets@v1", "格式"),
                       ("agent:nobody@v1", "不在账本")):
        r = verdict.resolve_node(led, spec)
        assert not r["ok"] and word in str(r["diag"]), (spec, r)
    # 主语无效、证据里有合法节点:主语仍无效,不拿证据节点顶替
    data = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t", "nodes": [
        {"node": "file:nope.ets@v1", "role": "进入·错", "reason": "r", "evidence": ["file:entry/A.ets@v1"]}]}]}
    built = _build(led, data)
    n0 = built["defects"][0]["nodes"][0]
    assert not n0["ok"] and n0["key"] is None and n0["reason"] == "r" and n0["evidence"][0]["status"] == "ok"
    assert built["roles"] == {}


def test_ambiguous_file_coordinates_never_bind_to_longest_history(tmp_path: Any) -> None:
    from migloop.filestory import FileStory
    led = _pool(tmp_path)
    original = led.stories["/proj/entry/A.ets"]
    led.stories["/other/entry/A.ets"] = FileStory("/other/entry/A.ets", original.versions + original.versions)
    for spec in ("file:A.ets@v1", "file:entry/A.ets@v1"):
        node = verdict.resolve_node(led, spec)
        assert not node["ok"] and node["key"] is None and "歧义" in node["diag"]
        assert verdict.resolve_evidence(led, spec)["status"] == "invalid"
    exact = verdict.resolve_node(led, "file:/proj/entry/A.ets@v1")
    assert exact["ok"] and exact["key"] == original.path
    assert not verdict.resolve_node(led, "file:/entry/A.ets@v1")["ok"]
    assert not verdict.resolve_node(led, "agent:__main__:@v1")["ok"]
    assert not verdict.resolve_node(led, "file:/proj/entry/A.ets@v" + "9" * 5000)["ok"]
    assert verdict.resolve_evidence(led, "#abcd:" + "9" * 5000 + "@L1")["status"] in ("invalid", "missing")


# ═══════════════ 证据引用:状态独立保留,不吞 ═══════════════

def test_evidence_refs_keep_their_own_status(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    cseq = _seq_of(led, "agent-c", "Write")
    good = _ref(led, cseq)
    forged = good.replace(f"@L{led.lines[cseq]}", "@L999999")
    data = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t", "nodes": [
        {"node": "agent:conv-a@v1", "role": "进入·错", "reason": "r",
         "evidence": [good, forged, f"#{cseq}@L{led.lines[cseq]}", "file:entry/A.ets@v1", "file:entry/A.ets@v7", "见上文"]}]}]}
    built = _build(led, data)
    n0 = built["defects"][0]["nodes"][0]
    assert n0["ok"]
    st = [(e["type"], e["status"]) for e in n0["evidence"]]
    assert st == [("action", "ok"), ("action", "missing"), ("action", "untagged"), ("node", "ok"), ("node", "invalid"), ("text", "unparsed")]
    assert n0["evidence"][0]["aid"] == "agent-c" and n0["evidence"][0]["seq"] == cseq and n0["evidence"][0]["v"] == 1
    assert n0["evidence_bad"] == 4
    # 主语有效但引用有错:主张保留(roles 里有),同时带无效引用计数,不标「核验通过」
    assert built["roles"]["agent-c"][0]["evidence_bad"] == 4 and built["roles"]["agent-c"][0]["checked"] == "not_checked"


# ═══════════════ 边:按账本核,相邻 ≠ 事实边 ═══════════════

def test_edges_checked_against_ledger_not_adjacency(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    data = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t", "nodes": [
        {"node": "file:spec/pages/A.md@v1", "role": "正常", "reason": "给了要求"},
        {"node": "agent:conv-a@v1", "role": "进入·错", "reason": "写错"},
        {"node": "file:entry/A.ets@v1", "role": "带病传递", "reason": "带着错"},
        {"node": f"agent:{MAIN_ID}@v1", "role": "正常", "reason": "派发词没问题"}],
        "edges": [{"from": f"agent:{MAIN_ID}@v1", "to": "agent:conv-a@v1", "relation": "派发"},
                  {"from": f"agent:{MAIN_ID}@v1", "to": "file:entry/A.ets@v1"},
                  {"from": "agent:conv-a@v1", "to": "file:entry/A.ets@v1", "relation": "派发"},
                  {"from": f"agent:{MAIN_ID}@v2", "to": "agent:conv-a@v1", "relation": "派发"},
                  {"from": "agent:nobody@v1", "to": "file:entry/A.ets@v1", "relation": "写"}]}]}
    built = _build(led, data)
    edges = built["defects"][0]["edges"]
    by = {(e["from"]["spec"], e["to"]["spec"]): e for e in edges}
    # 显式边
    assert by[(f"agent:{MAIN_ID}@v1", "agent:conv-a@v1")]["status"] == "true"
    assert by[(f"agent:{MAIN_ID}@v1", "file:entry/A.ets@v1")]["status"] == "false"          # 主会话没写 A.ets:未证实
    assert by[("agent:conv-a@v1", "file:entry/A.ets@v1")]["status"] == "false"                 # 关系词错:conv 是写不是派发
    assert by[(f"agent:{MAIN_ID}@v2", "agent:conv-a@v1")]["status"] == "false"                 # 派发版本不对
    assert by[("agent:nobody@v1", "file:entry/A.ets@v1")]["status"] == "not_checked"           # 端点无效
    # 相邻项自动补的隐式边:只是「核了一下」,标 implicit;显式写过的相邻对不重复核;核出来的关系与状态各自独立
    imp = [e for e in edges if e["implicit"]]
    assert [(e["from"]["spec"], e["to"]["spec"], e["relation"], e["status"]) for e in imp] == [
        ("file:spec/pages/A.md@v1", "agent:conv-a@v1", "读", "true")]      # A.ets→主会话 那一对已显式给过(反向),不重复核
    # 没给关系词的相邻对,账本里有写边就核成写
    data2 = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t", "nodes": [
        {"node": "agent:conv-a@v1", "role": "进入·错", "reason": "r"},
        {"node": "file:entry/A.ets@v1", "role": "带病传递", "reason": "r"}]}]}
    e0 = _build(led, data2)["defects"][0]["edges"][0]
    assert (e0["relation"], e0["status"], e0["implicit"]) == ("写", "true", True)


def test_read_edge_respects_feed_version_and_certainty(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    # fixer 读 A.ets@v1 喂 v1,再写 v2:读边到 fixer@v1 成立;到 fixer@v0 越界不核;conv 没读过 A.ets → false
    a = verdict.resolve_node(led, "file:entry/A.ets@v1")
    assert verdict.check_edge(led, a, verdict.resolve_node(led, "agent:fixer@v1"), "读")[0] == "true"
    assert verdict.check_edge(led, a, verdict.resolve_node(led, "agent:conv-a@v1"), "读")[0] == "false"
    # 写边:v2 的写者是 fixer v1;说成 conv 写的 → false 并说明真写者
    b = verdict.resolve_node(led, "file:entry/A.ets@v2")
    st, rel, note = verdict.check_edge(led, verdict.resolve_node(led, "agent:conv-a@v1"), b, "写")
    assert st == "false" and rel == "写" and "agent-f" in note
    assert verdict.check_edge(led, verdict.resolve_node(led, "agent:fixer@v1"), b, "写")[0] == "true"


# ═══════════════ 载荷:按缺陷 × 版本着色,修复前后不串色 ═══════════════

def _acceptance_block(led: atoms.Ledger) -> str:
    cseq = _seq_of(led, "agent-c", "Write")
    fseq = _seq_of(led, "agent-f", "Write")
    return _block(
        "schema: migloop-verdict/1\n"
        f"ledger: {atoms.ledger_identity(led)}\n"
        "root: file:entry/A.ets@v1\n"
        "defects:\n"
        "  - id: A\n"
        "    title: 返回键绕过\n"
        f"    repair: {{before: file:entry/A.ets@v1, after: file:entry/A.ets@v2, evidence: ['{_ref(led, fseq)}']}}\n"
        "    entry: [agent:conv-a@v1]\n"
        "    boundary: spec 是池外输入,停在这里\n"
        "    nodes:\n"
        "      - {node: file:spec/pages/A.md@v1, role: 正常, reason: 正确要求了拦截返回键}\n"
        f"      - {{node: agent:conv-a@v1, role: 进入·错, reason: 读了 spec 却没实现拦截, evidence: ['{_ref(led, cseq)}']}}\n"
        "      - {node: file:entry/A.ets@v1, role: 带病传递, reason: 缺拦截的版本被修复方读到}\n"
        "  - id: B\n"
        "    title: 进度条\n"
        "    repair: {before: file:entry/A.ets@v1, after: file:entry/A.ets@v2}\n"
        "    nodes:\n"
        "      - {node: agent:conv-a@v1, role: 正常, reason: 进度条按 spec 写了}\n"
        "      - {node: file:entry/A.ets@v1, role: 无法确认, reason: 内容未知}\n")


def test_payload_colors_by_defect_and_version(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    seq = [{"tool": "sessions", "input": {"file": "A.ets"}, "chars": 800},
           {"tool": "file", "input": {"path": "A.ets"}, "chars": 900},
           {"tool": "file", "input": {"path": "A.ets", "v": 1, "content": True}, "chars": 900},
           {"tool": "agent", "input": {"id": "conv-a", "v": 1}, "chars": 3000, "is_error": True}]
    p = probe.probe_payload(led, _run_dir(tmp_path, seq, _acceptance_block(led)))
    assert p["legacy"] is False and p["structured"]["errors"] == []
    s = p["structured"]
    assert s["identity"]["match"] is True and s["identity"]["current"] == atoms.ledger_identity(led)
    assert p["root"] == "/proj/entry/A.ets" and p["defects"] == {"A": "返回键绕过", "B": "进度条"}
    # 标注键 (缺陷, 种类, 身份, 版本):A.ets v1 在 A 下带病、在 B 下无法确认;v2 只在修复落点里,不在 roles
    roles = p["roles"]
    assert [(r["defect"], r["v"], r["role"]) for r in roles["/proj/entry/A.ets"]] == [("A", 1, "带病传递"), ("B", 1, "无法确认")]
    assert [(r["defect"], r["role"], r["entry"]) for r in roles["agent-c"]] == [("A", "进入·错", True), ("B", "正常", False)]
    assert roles["/proj/spec/pages/A.md"][0]["role"] == "正常"
    assert p["fixed"] == [{"defect": "A", "kind": "file", "key": "/proj/entry/A.ets", "v": 2},
                          {"defect": "B", "kind": "file", "key": "/proj/entry/A.ets", "v": 2}]
    assert not any(r["v"] == 2 for r in roles["/proj/entry/A.ets"])
    d0 = s["defects"][0]
    assert d0["repair"]["before"]["v"] == 1 and d0["repair"]["after"]["v"] == 2 and d0["repair"]["evidence"][0]["status"] == "ok"
    assert d0["entry"][0]["key"] == "agent-c" and d0["boundary"].startswith("spec 是池外")
    # 步骤层独立:索引 / 正文 / 失败分开记,失败的不算查过
    assert [(x["scope"], x["ok"]) for x in p["steps"]] == [("返修链", True), ("索引", True), ("正文 v1", True), ("v1", False)]
    # 旧散文字段还在(散文是附录),legacy 为 False
    assert p["links"] == [] and s["kind"] == "yaml" and "返回键绕过" in s["raw"]


def test_repair_after_cannot_be_marked_diseased(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    data = {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "t",
             "repair": {"before": "file:entry/A.ets@v1", "after": "file:entry/A.ets@v2"},
             "nodes": [{"node": "file:entry/A.ets@v2", "role": "带病传递", "reason": "r"},
                       {"node": "file:entry/A.ets@v1", "role": "带病传递", "reason": "r"}]}]}
    built = _build(led, data)
    n2, n1 = built["defects"][0]["nodes"]
    assert not n2["ok"] and "修复落点" in str(n2["diag"]) and n1["ok"]
    assert [r["v"] for r in built["roles"]["/proj/entry/A.ets"]] == [1]


def test_identity_mismatch_and_legacy_are_flagged(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    cur = atoms.ledger_identity(led)
    assert cur.startswith(atoms.LEDGER_CODE_VERSION) and cur == atoms.ledger_identity(led)
    # harness 落的 verdict.json 身份是旧的:主张保留,不绑定当前账本
    vj = {"kind": "json", "raw": "{}", "errors": [], "repaired": True, "harness_identity": "atoms-old:1:deadbeef",
          "data": {"schema": verdict.SCHEMA, "ledger": "atoms-old:1:deadbeef", "defects": [
              {"id": "A", "title": "t", "nodes": [{"node": "agent:conv-a@v1", "role": "进入·缺", "reason": "r"}]}]}}
    p = probe.probe_payload(led, _run_dir(tmp_path, [], "散文", vj))
    s = p["structured"]
    assert s["identity"]["match"] is False and s["identity"]["claimed"] == "atoms-old:1:deadbeef" and s["repaired"] is True
    assert p["roles"] == {} and p["legacy"] is False
    assert s["defects"][0]["nodes"][0]["role"] == "进入·缺"
    assert s["defects"][0]["nodes"][0]["key"] is None
    assert not s["identity"]["bound"]
    # 没有结论块:legacy,散文环照旧解析
    p2 = probe.probe_payload(led, _run_dir(tmp_path, [], "文件: entry/A.ets\n环 1  conv-a(agent-c)v1 写 A.ets@v1   判定: 错\n故障进入点: 环 1\n", name="legacy"))
    assert p2["legacy"] is True and p2["structured"] is None and p2["verdicts"]["agent-c"][0]["verdict"] == "错"
    # 块存在但校验失败:structured 带 errors、原文保留,roles 空,页面不整体报错
    p3 = probe.probe_payload(led, _run_dir(tmp_path, [], _block("schema: migloop-verdict/1\ndefects: [{id: A}]\n"), name="broken"))
    assert p3["legacy"] is False and p3["structured"]["errors"] and p3["roles"] == {} and "defects" in p3["structured"]["raw"]


@pytest.mark.parametrize("model,harness,expected", [
    ("current", "current", "matched"), ("current", None, "matched"),
    ("old", "current", "mismatch"), ("current", "old", "mismatch"),
    ("old", "old", "mismatch"), (None, "current", "missing"), (None, None, "missing"),
])
def test_identity_sources_never_override_each_other(tmp_path: Any, model: str | None,
                                                   harness: str | None, expected: str) -> None:
    led = _pool(tmp_path)
    current = atoms.ledger_identity(led)
    model = current if model == "current" else model
    harness = current if harness == "current" else harness
    data = {"schema": verdict.SCHEMA, "ledger": model, "root": "file:entry/A.ets@v2", "defects": [{
        "id": "A", "title": "t", "repair": {"before": "file:entry/A.ets@v1", "after": "file:entry/A.ets@v2",
                                              "evidence": ["file:entry/A.ets@v2"]},
        "entry": ["agent:conv-a@v1"],
        "nodes": [{"node": "agent:conv-a@v1", "role": "进入·错", "reason": "原始原因",
                   "evidence": [_ref(led, _seq_of(led, "agent-c", "Write"))],
                   "checks": [{"claim": "模型说已确认", "result": "true"}]}],
        "edges": [{"from": "agent:conv-a@v1", "to": "file:entry/A.ets@v1", "relation": "写"}]}]}
    built = verdict.build(led, data, [], {"harness_identity": harness})
    identity = built["identity"]
    assert identity["model"] == model and identity["harness"] == harness and identity["current"] == current
    assert identity["status"] == expected
    d = built["defects"][0]
    node = d["nodes"][0]
    assert node["reason"] == "原始原因" and node["role"] == "进入·错"
    assert node["checked"] == "not_checked" and node["checks"][0] == {
        "claim": "模型说已确认", "result": "true", "source": "model"}
    if expected == "matched":
        assert identity["bound"] and built["roles"] and built["fixed"]
        assert d["edges"][0]["status"] == "true"
    else:
        assert not identity["bound"] and built["roles"] == {} and built["fixed"] == []
        for subject in [built["root"], d["repair"]["before"], d["repair"]["after"], d["entry"][0], node,
                        d["edges"][0]["from"], d["edges"][0]["to"]]:
            assert not subject["ok"] and subject["key"] is None and subject["diag"]
        assert node["evidence"][0]["status"] == "not_checked"
        assert d["repair"]["evidence"][0]["status"] == "not_checked"
        assert d["edges"][0]["status"] == "not_checked"


def test_guide_and_sessions_carry_the_contract(tmp_path: Any) -> None:
    from migloop import atoms_text, mcp_server
    assert "schema: migloop-verdict/1" in mcp_server.GUIDE and "带病传递" in mcp_server.GUIDE and "repair" in mcp_server.GUIDE
    led = _pool(tmp_path)
    text = atoms_text.render_chains({"chains": [], "touched": []}, identity=atoms.ledger_identity(led))
    assert text.splitlines()[0] == f"账本身份: {atoms.ledger_identity(led)}"


def test_fixchain_template_has_verdict_hooks() -> None:
    from migloop.service import load_asset
    html = load_asset("fixchain.html")
    for needle in ("probeRolesFor(", "probeReason(", ".node.p-fixed", ".node.p-carry", ".node.p-ok", "修复落点",
                   "账本身份", "PROBE.roles", "legacy", "evidence", ".wire.cand"):
        assert needle in html, needle
