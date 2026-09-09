"""修复版本清单只保证账本内逐版有交代;区间端点不会抹掉中间修复。"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

import pytest

from migloop import atoms, coverage, filestory

PATH = "/project/entry/SplashPage.ets"


def splash_ledger() -> tuple[atoms.Ledger, list[dict[str, Any]]]:
    events = []
    agents = {name: atoms.AgentRec(id=name, session="synthetic") for name in ("agent-gen", "agent-fix")}
    for v in range(1, 55):
        agent = "agent-gen" if v <= 51 else "agent-fix"
        aver = v if v <= 51 else v - 51
        stage = "a2h-execute" if v <= 51 else "a2h-verify"
        content = (f"// generation {min(v, 51)}\n"
                   + f"image.width({100 if v <= 51 else 80})\n"
                   + f"mask.opacity({0 if v <= 52 else 0.4})\n"
                   + f"fullscreen({str(v >= 54).lower()})\n")
        ts = f"2026-01-01T00:00:{v:02d}Z"
        events.append(filestory.Ev(ts, v, "wfull", PATH, agent, content=content, aver=aver, stage=stage))
        agents[agent].actions.append(atoms.Action(ts, v, "Write", "write", ver=aver, at=aver, stage=stage,
                                                src=(f"/frozen/{agent}.jsonl", v * 2, v * 2 + 1), tuid=f"tool-{v}"))
    stories = filestory.build_stories(events)
    ledger = atoms.Ledger(stories=stories, agents=agents, locs={v: f"{v * 2 + 1}·fix" for v in range(1, 55)})
    for version in stories[PATH].versions:
        version.act_seq = version.seq
    chains = filestory.build_fix_chains(stories, {}, {}, root="/project")
    assert chains[0]["fix_versions"] == [52, 53, 54]
    return ledger, chains


def declaration(v: int, status: str = "explained", **change: Any) -> dict[str, Any]:
    return {"node": f"file:SplashPage.ets@v{v}", "status": status, "defects": ["A"],
            "reason": "显式理由,模块不验证其真伪", "evidence": [f"#fix:{v}@L{v * 2 + 1}"], **change}


def test_manifest_uses_each_fix_version_and_keeps_literal_changes_and_event_pointers() -> None:
    ledger, chains = splash_ledger()
    result = coverage.manifest(ledger, {"chains": chains}, "SplashPage.ets")
    assert result == coverage.manifest(ledger, chains, PATH)
    assert result["errors"] == [] and result["file"] == PATH
    assert [item["v"] for item in result["items"]] == [52, 53, 54]
    image, mask, _ = result["items"]
    assert image["node"] == f"file:{PATH}@v52" and image["before"] == f"file:{PATH}@v51"
    assert "image.width" in image["change"]["text"] and "mask.opacity" in mask["change"]["text"]
    assert image["content_known"] and image["source"] == "full" and image["stage"] == "a2h-verify"
    assert image["event"]["id"].endswith(":tool-52") and image["event"]["ref"] == "#fix:52@L105"
    assert image["event"]["use_line"] == 105 and image["event"]["result_line"] == 106
    assert "不保证" in result["scope"] and "不自动构成故障" in result["scope"]


def test_repair_endpoints_and_other_references_never_cover_middle_versions() -> None:
    ledger, chains = splash_ledger()
    manifest = coverage.manifest(ledger, chains, PATH)
    defects = [{"id": "A", "repair": {"before": f"file:{PATH}@v51", "after": f"file:{PATH}@v54"},
                "evidence": [f"file:{PATH}@v52", f"file:{PATH}@v53"]}]
    result = coverage.reconcile(ledger, manifest, [declaration(54)], defects, identity_bound=True)
    assert result["status"] == "incomplete" and result["complete"] is False
    assert result["missing"] == [f"file:{PATH}@v52", f"file:{PATH}@v53"]
    assert result["counts"]["accounted"] == 1
    old = coverage.reconcile(ledger, manifest, None, defects, identity_bound=True)
    assert old["status"] == "unprovided" and not old["complete"]
    assert old["missing"] == [item["node"] for item in manifest["items"]]


def test_unknown_content_and_missing_event_are_explicit_not_guessed_from_version_seq() -> None:
    ledger, chains = splash_ledger()
    version = ledger.stories[PATH].versions[52]
    version.source, version.content, version.diff, version.diff_kind = "opaque", None, None, "unknown"
    version.act_seq = None
    item = coverage.manifest(ledger, chains, PATH)["items"][1]
    assert item["content_known"] is False and "未知" in item["change"]["text"]
    assert item["change"]["literal"] is False and item["change"]["semantic_checked"] is False
    assert item["event"]["status"] == "unavailable" and item["event"]["ref"] is None


def test_manifest_preserves_exact_chain_membership_without_filling_version_ranges() -> None:
    ledger, chains = splash_ledger()
    subset = [{**chains[0], "fix_versions": [54, 52, 52]}, {**chains[0], "fix_versions": [52]}]
    result = coverage.manifest(ledger, subset, PATH)
    assert [item["v"] for item in result["items"]] == [52, 54]
    assert result["items"][1]["before"] == f"file:{PATH}@v53"   # 前一版信息不是覆盖清单成员


def test_multiple_versions_from_one_original_event_still_require_separate_rows() -> None:
    ledger, chains = splash_ledger()
    ledger.stories[PATH].versions[52].act_seq = 52
    manifest = coverage.manifest(ledger, chains, PATH)
    assert manifest["items"][0]["event"]["id"] == manifest["items"][1]["event"]["id"]
    result = coverage.reconcile(ledger, manifest, [declaration(52), declaration(54)], ["A"], identity_bound=True)
    assert result["missing"] == [f"file:{PATH}@v53"] and not result["complete"]


def test_reconcile_reports_each_structural_problem_separately() -> None:
    ledger, chains = splash_ledger()
    manifest = coverage.manifest(ledger, chains, PATH)
    rows = [declaration(52, status="done", reason=" ", defects=["ghost"]),
            declaration(52, node=f"file:{PATH}@v52"), declaration(54, status="unresolved"),
            declaration(51), declaration(999)]
    result = coverage.reconcile(ledger, manifest, rows, ["A"], identity_bound=True)
    assert result["status"] == "invalid" and not result["complete"]
    assert result["missing"] == [f"file:{PATH}@v53"]
    assert len(result["duplicates"]) == 1 and result["duplicates"][0]["rows"] == [0, 1]
    assert len(result["out_of_scope"]) == 2
    assert len(result["invalid_status"]) == len(result["empty_reason"]) == len(result["unknown_defects"]) == 1
    assert result["unknown_defects"][0]["defect"] == "ghost"
    assert result["counts"]["accounted"] == 1 and result["unresolved"] == [f"file:{PATH}@v54"]


def test_complete_means_accounted_not_resolved_or_semantically_certified() -> None:
    ledger, chains = splash_ledger()
    manifest = coverage.manifest(ledger, chains, PATH)
    rows = [declaration(52), declaration(53, status="unresolved", defects=[], evidence=[]),
            declaration(54, status="not_repair", defects=[], reason="阶段后新增,不主张原有故障", evidence=[])]
    result = coverage.reconcile(ledger, manifest, rows, [{"id": "A"}], identity_bound=True)
    assert result["status"] == "complete" and result["complete"]
    assert result["unresolved"] == [f"file:{PATH}@v53"] and result["not_repair"] == [f"file:{PATH}@v54"]
    assert result["semantic_checked"] is False and result["evidence_checked"] is False


def test_unbound_identity_and_stale_manifest_cannot_claim_completion() -> None:
    ledger, chains = splash_ledger()
    manifest = coverage.manifest(ledger, chains, PATH)
    rows = [declaration(v) for v in (52, 53, 54)]
    unbound = coverage.reconcile(ledger, manifest, rows, {"A": "title"})
    assert unbound["status"] == "unbound" and not unbound["complete"]
    stale = coverage.reconcile(ledger, {**manifest, "ledger": "other-ledger"}, rows, ["A"], identity_bound=True)
    assert stale["status"] == "invalid_manifest" and not stale["complete"]


def test_malformed_coverage_stays_missing_and_processing_is_bounded(monkeypatch: Any) -> None:
    ledger, chains = splash_ledger()
    manifest = coverage.manifest(ledger, chains, PATH)
    bad = coverage.reconcile(ledger, manifest, "A covers v51-v54", ["A"], identity_bound=True)
    assert len(bad["missing"]) == 3 and bad["invalid_rows"]
    wrong = coverage.reconcile(ledger, manifest, [None, {"node": f"file:{PATH}@v52", "status": "explained", "reason": "r"}],
                               ["A"], identity_bound=True)
    assert wrong["invalid_rows"] and wrong["counts"]["accounted"] == 0
    monkeypatch.setattr(coverage, "MAX_ROWS", 2)
    limited = coverage.reconcile(ledger, manifest, [declaration(v) for v in (52, 53, 54)], ["A"], identity_bound=True)
    assert limited["invalid_rows"] and limited["missing"] == [f"file:{PATH}@v54"]


def test_manifest_rejects_ambiguous_or_stale_inputs_and_bounds_literal_diff() -> None:
    ledger, chains = splash_ledger()
    assert coverage.manifest(ledger, chains, "missing.ets")["errors"]
    assert coverage.manifest(ledger, None, PATH)["errors"]
    stale = coverage.manifest(ledger, [{**chains[0], "fix_versions": [52, 999, True]}], PATH)
    assert {error["code"] for error in stale["errors"]} == {"missing_ledger_version", "invalid_fix_version"}
    ledger.stories["/other/SplashPage.ets"] = filestory.FileStory("/other/SplashPage.ets")
    assert "歧义" in coverage.manifest(ledger, chains, "SplashPage.ets")["errors"][0]["message"]
    ledger.stories[PATH].versions[51].diff = "\n".join("+" + "x" * 400 for _ in range(40))
    changed = coverage.manifest(ledger, chains, PATH)["items"][0]["change"]
    assert changed["truncated"] and len(changed["text"]) <= coverage.DIFF_CHARS


def candidate_action(ledger: atoms.Ledger, seq: int, *, tool: str = "Bash", kind: str = "other",
                     touch: bool = False, cls: str = "out", by: str = "agent-fix",
                     ts: str = "2026-01-01T00:01:00Z", token: str = PATH,
                     ambiguous: bool = False) -> atoms.Action:
    ledger.agents.setdefault(by, atoms.AgentRec(id=by, session="synthetic"))
    action = atoms.Action(ts, seq, tool, kind, at=4, stage="a2h-verify",
                          src=(f"/frozen/{by}.jsonl", seq * 2, seq * 2 + 1), tuid=f"candidate-tool-{seq}",
                          detail={"cmd": "opaque script with an exact output target"})
    ledger.agents[by].actions.append(action)
    ledger.locs[seq] = f"{seq * 2 + 1}·fix"
    ledger.mentions.setdefault(PATH, []).append(atoms.Mention(ts, seq, by, 4, token, "exact target cue",
                                                            ambiguous=ambiguous, where="out", cls=cls))
    if touch:
        ledger.stories[PATH].touches.append(filestory.Touch(ts, seq, by, 4, "方向未知", "a2h-verify"))
    return action


def candidate_declaration(item: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    return {"candidate": item["id"], "status": "unresolved", "defects": [], "reason": "尚未核原始效应",
            "evidence": [item["ref"]], **overrides}


def test_candidates_dedupe_touch_and_mentions_without_creating_versions_or_claiming_repairs() -> None:
    ledger, chains = splash_ledger()
    logo = candidate_action(ledger, 100, touch=True, cls="body")
    ledger.mentions[PATH].append(atoms.Mention(logo.ts, 100, "agent-fix", 4, PATH, "ok target", where="out", cls="out"))
    mask = candidate_action(ledger, 101, kind="write")
    mask.files = [atoms.FileRef("write", "/tmp/patch_mask.py",
                                filestory.Ev(mask.ts, 102, "wfull", "/tmp/patch_mask.py", "agent-fix"), v=1)]
    manifest = coverage.manifest(ledger, chains, PATH)
    assert [item["seq"] for item in manifest["candidates"]] == [100, 101]
    first, second = manifest["candidates"]
    eid = atoms.event_id(ledger, "agent-fix", 100)
    assert first["id"] == "candidate:" + hashlib.sha256((eid + "\0" + PATH).encode()).hexdigest()[:20]
    assert first["source"] == "touch" and first["sources"] == ["touch", "mention"]
    assert second["source"] == "mention" and second["event"]["use_line"] == 203
    assert first["ref"] == "#fix:100@L201" and first["phase"] == "a2h-verify"
    assert "全动作窗口" in first["window_scope"] and "不保证" in first["window_scope"]
    assert not first["repair_confirmed"] and not first["writer_confirmed"]
    assert len(ledger.stories[PATH].versions) == 54 and [v["v"] for v in manifest["items"]] == [52, 53, 54]


def test_candidates_exclude_confirmed_reads_other_native_targets_ambiguous_and_outside_actors() -> None:
    ledger, chains = splash_ledger()
    for seq, tool in enumerate(("Read", "Grep", "Glob"), 100):
        candidate_action(ledger, seq, tool=tool, touch=True)
    candidate_action(ledger, 103, kind="read")
    candidate_action(ledger, 104, cls="readonly")
    for seq, tool in enumerate(("Write", "Edit", "MultiEdit"), 105):
        action = candidate_action(ledger, seq, tool=tool, kind="write", touch=True)
        other = "/project/other.ets"
        action.files = [atoms.FileRef("write", other, filestory.Ev(action.ts, seq, "wfull", other, "agent-fix"))]
    candidate_action(ledger, 108, by="outside-fixer", touch=True)
    candidate_action(ledger, 109, ambiguous=True)
    candidate_action(ledger, 110, token="/other/SplashPage.ets")
    # file_atom 中一次无歧义后缀命中,若原始 cwd 指向另一个绝对文件,也不能借来。
    conflict = candidate_action(ledger, 111)
    conflict.detail["mentions"] = [(PATH, "exact target cue", "/other/SplashPage.ets", "out", "out")]
    candidate_action(ledger, 112)
    manifest = coverage.manifest(ledger, chains, PATH)
    assert [item["seq"] for item in manifest["candidates"]] == [112]


def test_formal_versions_suppress_same_event_candidates_even_when_chain_lists_subset() -> None:
    ledger, chains = splash_ledger()
    original = ledger.agents["agent-fix"].actions[0]
    ledger.stories[PATH].touches.append(filestory.Touch(original.ts, 52, "agent-fix", 1, "候选重复"))
    ledger.mentions[PATH] = [atoms.Mention(original.ts, 52, "agent-fix", 1, PATH, "same event", cls="out")]
    manifest = coverage.manifest(ledger, [{**chains[0], "fix_versions": [53, 54]}], PATH)
    assert manifest["candidates"] == []


def test_candidate_window_uses_fix_after_not_first_recorded_repair_or_phase_guess() -> None:
    ledger, chains = splash_ledger()
    candidate_action(ledger, 100, ts="2026-01-01T00:00:10Z", touch=True)
    candidate_action(ledger, 101, ts="2025-12-31T19:00:20-05:00")
    ledger.fix_after = "2026-01-01T00:00:20Z"
    bounded = coverage.manifest(ledger, chains, PATH)
    assert [item["seq"] for item in bounded["candidates"]] == [101]
    assert "时间 >= fix_after" in bounded["candidate_scope"]["window_scope"]
    ledger.fix_after = None
    full = coverage.manifest(ledger, chains, PATH)
    assert [item["seq"] for item in full["candidates"]] == [100, 101]
    assert "无明确阶段时间边界" in full["candidate_scope"]["window_scope"]
    assert coverage.manifest(ledger, [{**chains[0], "fixers_all": []}], PATH)["candidates"] == []


def test_candidate_identity_survives_local_action_renumbering() -> None:
    ledger, chains = splash_ledger()
    action = candidate_action(ledger, 100)
    before = coverage.manifest(ledger, chains, PATH)["candidates"][0]["id"]
    action.seq = 1000
    ledger.mentions[PATH][0].seq = 1000
    after = coverage.manifest(ledger, chains, PATH)["candidates"][0]["id"]
    assert before == after


def test_union_coverage_requires_candidates_individually_and_preserves_legacy_version_manifest() -> None:
    ledger, chains = splash_ledger()
    candidate_action(ledger, 100, touch=True)
    candidate_action(ledger, 101)
    manifest = coverage.manifest(ledger, chains, PATH)
    versions = [declaration(v) for v in (52, 53, 54)]
    only_versions = coverage.reconcile(ledger, manifest, versions, ["A"], identity_bound=True)
    cids = [item["id"] for item in manifest["candidates"]]
    assert only_versions["missing"] == only_versions["missing_candidates"] == cids
    assert only_versions["missing_versions"] == [] and not only_versions["complete"]
    assert only_versions["counts"]["expected_versions"] == 3 and only_versions["counts"]["expected_candidates"] == 2
    assert only_versions["counts"]["missing_versions"] == 0 and only_versions["counts"]["missing_candidates"] == 2
    rows = versions + [candidate_declaration(manifest["candidates"][0]),
                       candidate_declaration(manifest["candidates"][1], status="not_repair")]
    result = coverage.reconcile(ledger, manifest, rows, ["A"], identity_bound=True)
    assert result["complete"] and result["counts"]["accounted"] == 5 and not result["semantic_checked"]
    assert result["rows"][-1]["canonical_node"] is None and result["rows"][-1]["canonical_candidate"] == cids[1]
    assert result["unresolved"] == cids[:1] and result["not_repair"] == cids[1:]
    assert not coverage.reconcile(ledger, manifest, rows, ["A"])["complete"]
    unprovided = coverage.reconcile(ledger, manifest, None, ["A"], identity_bound=True)
    assert unprovided["status"] == "unprovided" and len(unprovided["missing"]) == 5
    legacy = {k: v for k, v in manifest.items() if k not in ("candidates", "candidate_scope")}
    assert coverage.reconcile(ledger, legacy, versions, ["A"], identity_bound=True)["complete"]


def test_candidate_rows_use_same_validation_and_exactly_one_target_key() -> None:
    ledger, chains = splash_ledger()
    candidate_action(ledger, 100)
    manifest = coverage.manifest(ledger, chains, PATH)
    candidate = manifest["candidates"][0]
    rows = [candidate_declaration(candidate, status="done", reason=" ", defects=["ghost"]),
            candidate_declaration(candidate), candidate_declaration(candidate, candidate="candidate:" + "0" * 20),
            candidate_declaration(candidate, node=f"file:{PATH}@v52"),
            {"status": "unresolved", "defects": [], "reason": "missing target", "evidence": []}]
    result = coverage.reconcile(ledger, manifest, rows, ["A"], identity_bound=True)
    assert not result["complete"] and result["status"] == "invalid"
    assert result["duplicates"][0]["candidate"] == candidate["id"]
    assert result["invalid_status"] and result["empty_reason"] and result["unknown_defects"]
    assert len(result["out_of_scope"]) == 3 and len(result["invalid_rows"]) == 2
    assert result["counts"]["accounted"] == 0 and len(result["missing_versions"]) == 3


def text_candidate(ledger: atoms.Ledger, seq: int, kind: str = "say", **kwargs: Any) -> atoms.Action:
    action = candidate_action(ledger, seq, tool=kind, kind=kind, cls="text", **kwargs)
    action.tuid = None
    action.detail = {"text": "我已经在外部手工修改了这个文件;这里只是一条待查的主张"}
    return action


def test_nonexecution_text_excluded_by_event_type_but_claims_and_mentions_remain() -> None:
    ledger, chains = splash_ledger()
    kinds = ("think", "say", "inbox", "instruction", "inject", "system", "notify", "interrupt")
    for seq, kind in enumerate(kinds, 100):
        action = text_candidate(ledger, seq, kind)
        if kind == "inject":
            source = "/project/.claude/skills/demo/SKILL.md"
            action.files = [atoms.FileRef("read", source, filestory.Ev(action.ts, 200, "read", source, "agent-fix"))]
    # 同一事件多条提及只能排除计数一次,并且不得从原提及索引删除任何一条。
    ledger.mentions[PATH].append(deepcopy(ledger.mentions[PATH][0]))
    mentions_before = deepcopy(ledger.mentions)
    manifest = coverage.manifest(ledger, chains, PATH)
    assert manifest["candidates"] == []
    assert manifest["policy"] == "execution-candidates/2"
    assert manifest["candidate_scope"]["excluded_nonexecution"] == {kind: 1 for kind in kinds}
    assert "不证明" in manifest["candidate_scope"]["nonexecution_boundary"]
    assert ledger.mentions == mentions_before
    assert all(action.detail.get("text") for action in ledger.agents["agent-fix"].actions if action.seq >= 100)


@pytest.mark.parametrize("risk", ["tuid", "kind", "write", "delete", "touched", "conditional",
                                 "conditional_reads", "write_capable", "unfinished", "unresolved", "failed", "pending"])
def test_nonexecution_exclusion_keeps_event_with_conflicting_effect_or_risk_marker(risk: str) -> None:
    ledger, chains = splash_ledger()
    action = text_candidate(ledger, 100)
    if risk == "tuid":
        action.tuid = "actual-tool-call"
    elif risk == "kind":
        action.kind = "other"
    elif risk in {"write", "delete"}:
        action.files = [atoms.FileRef(risk, PATH, filestory.Ev(action.ts, 101, "wopaque", PATH, "agent-fix"))]
    elif risk in {"failed", "pending"}:
        action.ok = False if risk == "failed" else None
    else:
        action.detail[risk] = [PATH] if risk in {"touched", "conditional", "conditional_reads"} else True
    manifest = coverage.manifest(ledger, chains, PATH)
    assert [candidate["seq"] for candidate in manifest["candidates"]] == [100]
    assert manifest["candidate_scope"]["excluded_nonexecution"] == {}


@pytest.mark.parametrize("tool,kind", [("Bash", "other"), ("PowerShell", "other"), ("exec", "other"),
                                      ("Skill", "skill"), ("SendMessage", "message"),
                                      ("Agent", "dispatch"), ("Task", "dispatch")])
def test_execution_calls_are_not_removed_even_when_their_text_is_a_plan_or_summary(tool: str, kind: str) -> None:
    ledger, chains = splash_ledger()
    action = candidate_action(ledger, 100, tool=tool, kind=kind, cls="out", touch=True)
    action.detail = {"text": "计划和收尾文字不会把真实工具调用变成非执行记录", "conditional": [PATH]}
    action.ok = False
    manifest = coverage.manifest(ledger, chains, PATH)
    assert [candidate["seq"] for candidate in manifest["candidates"]] == [100]
    assert manifest["candidate_scope"]["excluded_nonexecution"] == {}


def test_nonexecution_counts_only_exact_eligible_actor_window_and_does_not_drop_mixed_tool_block() -> None:
    ledger, chains = splash_ledger()
    ledger.fix_after = "2026-01-01T00:00:50Z"
    text_candidate(ledger, 100, ts="2026-01-01T00:00:10Z")
    text_candidate(ledger, 101, by="outside-actor")
    text_candidate(ledger, 102, ambiguous=True)
    thought = text_candidate(ledger, 103, "think")
    write = candidate_action(ledger, 104, tool="Edit", kind="write", touch=True)
    write.src = (thought.src[0], thought.src[1], thought.src[1] + 1)
    write.blk = 1  # 同一物理消息中的第二块是真实工具调用,不能随第一块 think 删除。
    manifest = coverage.manifest(ledger, chains, PATH)
    assert [candidate["seq"] for candidate in manifest["candidates"]] == [104]
    assert manifest["candidate_scope"]["excluded_nonexecution"] == {"think": 1}


def test_legacy_manifest_without_policy_keeps_its_saved_denominator() -> None:
    ledger, chains = splash_ledger()
    action = candidate_action(ledger, 100)
    action.tuid = None
    legacy = coverage.manifest(ledger, chains, PATH)
    legacy.pop("policy", None)
    action.tool = action.kind = "say"
    fresh = coverage.manifest(ledger, chains, PATH)
    assert fresh["policy"] == "execution-candidates/2" and fresh["candidates"] == []
    rows = [declaration(v) for v in (52, 53, 54)]
    checked = coverage.reconcile(ledger, legacy, rows, ["A"], identity_bound=True)
    assert checked["missing_candidates"] == [legacy["candidates"][0]["id"]]
    assert not checked["complete"]  # 不因新策略从旧清单里删掉一项或自动补 not_repair。
