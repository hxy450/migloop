"""Draft feedback is a read-only check, not a semantic approval or navigation."""
import asyncio
from copy import deepcopy
import json

import pytest

from migloop import atoms, draft_check, mcp_server, probe, service, verdict
from tests.test_verdict import _pool, _ref, _seq_of


def data(ledger):
    return {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger),
            "root": "file:A.ets@v2", "defects": [{"id": "A", "title": "test", "entry": [],
             "nodes": [{"node": "agent:agent-c@v1", "role": "正常", "reason": "model statement",
                        "evidence": [_ref(ledger, _seq_of(ledger, "agent-c", "Write"))]}]}]}


def recorded(ledger, body, **changes):
    row = {"tool": "check", "call_id": "check-call", "input": {"draft": body}, "has_result": True,
           "text": draft_check.render(ledger, body), "provenance": {"complete_pair": True,
           "tool_origin": {"verified": True, "leaf": "check"}}, "is_error": False}
    row.update(changes)
    return row


def test_bad_coordinate_and_locator_are_reported_without_reading_raw_or_mutating(tmp_path, monkeypatch):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    doc["defects"][0]["nodes"].append({"node": "agent:agent-c@v99", "role": "无法确认",
                                     "reason": "unproven", "evidence": ["#unknown:99@L3"]})
    before = deepcopy((ledger, doc))
    monkeypatch.setattr(atoms, "action_raw", lambda *a, **k: pytest.fail("checker must not open original bodies"))
    result = draft_check.evaluate(ledger, json.dumps(doc))
    assert {r["code"] for r in result["issues"]} == {"invalid_node", "invalid_reference"}
    assert result["semantic_checked"] is False and result["status"] == "needs_review"
    assert (ledger, doc) == before
    assert "model statement" not in json.dumps(result)
    assert probe._step_node(ledger, "check", {"draft": json.dumps(doc), "file": "A.ets"}) is None


def test_well_formed_claim_is_not_semantically_certified_and_final_swap_is_visible(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    body = json.dumps(doc)
    result = draft_check.evaluate(ledger, body)
    assert result["status"] == "mechanical_clear" and result["semantic_checked"] is False
    calls = [recorded(ledger, body)]
    bound = draft_check.final_binding(ledger, calls, doc, identity_bound=True)
    assert bound["status"] == "matched" and bound["matched_check"] == 1
    # Mapping key order or YAML/JSON formatting does not matter; text claims do.
    assert draft_check.document_hash(json.loads(json.dumps(doc, sort_keys=True))) == result["document_sha256"]
    changed = deepcopy(doc)
    changed["defects"][0]["nodes"][0]["reason"] = "unchecked new assertion"
    assert draft_check.final_binding(ledger, calls, changed, identity_bound=True)["status"] == "mismatch"
    calls.append(recorded(ledger, json.dumps(changed)))
    assert draft_check.final_binding(ledger, calls, doc, identity_bound=True)["status"] == "mismatch"


@pytest.mark.parametrize("mode", ["missing", "partial", "error", "foreign", "unpaired", "changed_output", "wrong_hash", "unbound", "contradictory_status"])
def test_untrusted_check_cannot_certify_final(tmp_path, mode):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    call = recorded(ledger, json.dumps(doc))
    if mode == "missing": call["has_result"] = False
    if mode == "partial": call["delivery_truncated"] = True
    if mode == "error": call["is_error"] = True
    if mode == "foreign": call["provenance"]["tool_origin"]["verified"] = False
    if mode == "unpaired": call["provenance"]["complete_pair"] = False
    if mode == "changed_output": call["text"] = "not JSON"
    if mode == "wrong_hash":
        result = json.loads(call["text"]); result["document_sha256"] = "wrong"; call["text"] = json.dumps(result)
    if mode == "contradictory_status":
        result = json.loads(call["text"]); result["status"] = "needs_review"; call["text"] = json.dumps(result)
    result = draft_check.final_binding(ledger, [call], doc, identity_bound=mode != "unbound")
    assert result["status"] == "unverifiable" and result["matched_check"] is None


def test_bounds_identity_and_schema_fail_closed(tmp_path, monkeypatch):
    ledger = _pool(tmp_path)
    for body in ("", "x" * (draft_check.MAX_CHARS + 1), None, "schema: ["):
        result = draft_check.evaluate(ledger, body)
        assert result["status"] == "needs_review" and result["counts"]["errors"]
    doc = data(ledger); doc["ledger"] = "different"
    monkeypatch.setattr(verdict, "resolve_evidence", lambda *a: pytest.fail("unbound must not resolve"))
    result = draft_check.evaluate(ledger, json.dumps(doc))
    assert [r["code"] for r in result["issues"]] == ["identity"]


def test_basis_is_checked_as_structure_and_positions_not_truth(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger); n = doc["defects"][0]["nodes"][0]; n["role"] = "进入·错"
    result = draft_check.evaluate(ledger, json.dumps(doc))
    assert "missing_causal_basis" in [r["code"] for r in result["issues"]]
    n["basis"] = {"expected": "required", "actual": "different output", "counterevidence": "not fully checked",
                  "expected_evidence": n["evidence"], "actual_evidence": ["#fake:0@L0"]}
    result = draft_check.evaluate(ledger, json.dumps(doc))
    assert "invalid_reference" in [r["code"] for r in result["issues"]]
    n["basis"]["actual_evidence"] = n["evidence"]
    result = draft_check.evaluate(ledger, json.dumps(doc))
    assert result["status"] == "mechanical_clear" and result["semantic_checked"] is False


def test_mcp_and_http_share_check_without_opening_nodes(tmp_path, monkeypatch):
    ledger = _pool(tmp_path); body = json.dumps(data(ledger))
    class Backend:
        async def get_ledger(self, sid): return ledger
        async def get_session_cwd(self, sid): return "/proj"
        async def get_fixchain(self, sid): return {"chains": []}
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    monkeypatch.setattr(service, "fixchain_payload", lambda _: {"chains": []})
    async def run():
        server = mcp_server.build_server(Backend())
        checked = await server.call_tool("check", {"sid": "s", "draft": body})
        opened = await server.call_tool("file", {"sid": "s", "path": "A.ets", "v": 2, "via": "sessions"})
        return checked[0].text, opened[0].text
    checked, opened = asyncio.run(run())
    assert opened.startswith("# 文件")  # check did not consume first-open privilege.
    assert checked == service.atom_text("unused", "check", {"draft": body})
    assert json.loads(checked) == service.atom_json("unused", "check", {"draft": body})


def test_issue_truncation_is_explicit(tmp_path):
    ledger = _pool(tmp_path); doc = data(ledger)
    doc["defects"][0]["nodes"] *= 60
    for n in doc["defects"][0]["nodes"]: n["node"] = "file:missing.ets@v1"
    result = draft_check.evaluate(ledger, json.dumps(doc))
    assert len(result["issues"]) == draft_check.MAX_ISSUES and result["omitted_issues"] == 20
    assert result["counts"]["errors"] == 60


def test_missing_coverage_rows_are_not_a_clear_check():
    from tests.test_repair_coverage import splash_ledger, PATH

    ledger, chains = splash_ledger()
    doc = {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger),
           "root": f"file:{PATH}@v54", "defects": [], "coverage": []}
    result = draft_check.evaluate(ledger, json.dumps(doc), {"chains": chains}, PATH)
    assert result["coverage"]["counts"]["missing"] == 3
    assert any(r["code"] == "coverage_incomplete" for r in result["issues"])
