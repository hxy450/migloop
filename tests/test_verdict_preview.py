"""Local preview is not schema repair, submission authentication, or causality."""
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from migloop import draft_check, verdict_preview, verdict_v3
from tests.test_verdict import _pool
from tests.test_verdict_v3 import document, raw_ref


def original_hash(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    ledger = _pool(tmp_path)
    def forbidden(*_args, **_kwargs):
        pytest.fail("preview must not call full build or change inventory")
    monkeypatch.setattr(verdict_v3, "build", forbidden)
    monkeypatch.setattr(verdict_v3, "_changes", forbidden)
    return ledger, document(ledger)


@pytest.mark.parametrize("defect", ["coverage_links", "top_unknown", "coverage_reason", "finding_counterevidence"])
def test_local_schema_errors_do_not_erase_independently_valid_nodes(prepared, defect):
    ledger, data = prepared
    if defect == "coverage_links":
        data["coverage"] = [{"event": "e1", "finding": "B,C", "status": "explained", "reason": "original"},
                            {"event": "e1", "finding": "F", "status": "explained", "reason": "another claim"}]
    elif defect == "top_unknown":
        data["unknown"] = ["original top-level uncertainty"]
    elif defect == "coverage_reason":
        data["coverage"] = [{"event": "e1", "finding": "F", "status": "explained"}]
    else:
        data["findings"][0]["counterevidence"] = ["original finding-level contrary claim"]
    before = deepcopy(data)
    raw = "  " + json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    got = verdict_preview.build(ledger, data, raw=raw)
    graph = got["argument_graph"]
    assert got["partial_document"] and not got["original_schema_valid"] and got["strict_status"] == "failed"
    assert got["schema_errors"] == verdict_v3.validate(data)
    assert len(graph["nodes"]) == 3 and all(n["binding"]["status"] == "matched" for n in graph["nodes"])
    assert [n["id"] for n in graph["nodes"]] == ["F/spec", "F/actor", "F/file"]
    assert all(e["binding"]["status"] == "confirmed" for e in graph["edges"])
    assert all(not e["semantic_checked"] and not e["propagation"]["semantic_checked"] for e in graph["edges"])
    assert got["raw"] == raw and got["raw_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert got["original_document"] == data and got["document_sha256"] == original_hash(data)
    assert got["strict_document_sha256"] is None and draft_check.document_hash(data) is None
    assert graph["document_sha256"] == got["original_document_sha256"]
    assert got["identity"]["bound"] and data == before
    assert graph["coverage_checked"] is False
    if defect.startswith("coverage"):
        assert all(c["status"] == "invalid" and c["binding"]["status"] == "invalid" for c in graph["coverage"])
    else:
        assert len(graph["model_remarks"]) == 1 and graph["model_remarks"][0]["used_for_binding"] is False


def test_preview_hash_is_original_not_the_legitimate_subset(prepared):
    ledger, data = prepared
    valid_hash = draft_check.document_hash(data)
    data["unknown"] = "not a schema-v3 field"
    got = verdict_preview.build(ledger, data)
    assert got["document_sha256"] != valid_hash
    assert got["document_sha256"] == original_hash(data)
    assert got["original_document"]["unknown"] == data["unknown"]


def test_duplicate_finding_ids_keep_every_declaration_ambiguous(prepared):
    ledger, data = prepared
    data["findings"].append(deepcopy(data["findings"][0]))
    got = verdict_preview.build(ledger, data)["argument_graph"]
    assert len(got["nodes"]) == 6 and len({n["id"] for n in got["nodes"]}) == 6
    assert all(n["binding"]["status"] == "ambiguous" and n["display_id_only"] for n in got["nodes"])
    assert all(f["declared_id"] == "F" and f["id_status"] == "ambiguous" for f in got["findings"])
    assert got["edges"] == [] and len(got["edge_declarations"]) == 4
    assert all(not e["drawable"] for e in got["edge_declarations"])


def test_duplicate_node_ids_are_not_resolved_by_first_or_last_wins(prepared):
    ledger, data = prepared
    data["findings"][0]["nodes"][1]["id"] = "spec"
    graph = verdict_preview.build(ledger, data)["argument_graph"]
    assert len(graph["nodes"]) == 3
    ambiguous = [n for n in graph["nodes"] if n["local_id"] == "spec"]
    assert len(ambiguous) == 2 and all(n["binding"]["status"] == "ambiguous" for n in ambiguous)
    assert ambiguous[0]["id"] != ambiguous[1]["id"]
    assert graph["edges"] == [] and len(graph["edge_declarations"]) == 2


def test_bad_finding_does_not_taint_a_different_unique_finding(prepared):
    ledger, data = prepared
    valid = deepcopy(data["findings"][0])
    valid["id"] = "independent"
    data["findings"].extend([deepcopy(data["findings"][0]), valid])
    graph = verdict_preview.build(ledger, data)["argument_graph"]
    assert [n["binding"]["status"] for n in graph["nodes"] if n["finding"] == "independent"] == ["matched"] * 3
    assert len(graph["edges"]) == 2 and all(e["finding"] == "independent" for e in graph["edges"])


@pytest.mark.parametrize("fault", ["ledger", "harness", "trace", "target_missing", "target_time", "target_extra", "target_path", "schema"])
def test_global_identity_or_target_fault_never_binds_any_local_node(prepared, fault):
    ledger, data = prepared
    meta = {}
    if fault == "ledger": data["ledger"] = "wrong-ledger"
    elif fault == "harness": meta["harness_identity"] = "wrong-ledger"
    elif fault == "trace": meta["trace_identity"] = {"bound": False}
    elif fault == "target_missing": del data["target"]
    elif fault == "target_time": data["target"]["at"] = "latest"
    elif fault == "target_extra": data["target"]["v"] = 1
    elif fault == "target_path": data["target"]["file"] = "../A.ets"
    else: data["schema"] = "migloop-verdict/2"
    got = verdict_preview.build(ledger, data, meta=meta)
    assert got["identity"]["bound"] is False
    assert all(n["binding"]["status"] == "unbound" for n in got["argument_graph"]["nodes"])
    assert all(e["binding"]["status"] == "unbound" for e in got["argument_graph"]["edges"])
    assert all(r["status"] == "unbound" for n in got["argument_graph"]["nodes"] for r in n["evidence"])


def test_agent_to_agent_write_is_retained_as_invalid_declaration_not_a_drawable_edge(prepared):
    ledger, data = prepared
    finding = data["findings"][0]
    actor = deepcopy(finding["nodes"][1])
    actor["id"] = "other"
    finding["nodes"] = [finding["nodes"][1], actor]
    finding["edges"] = [{"from": "actor", "to": "other", "relation": "write", "claim": "unsupported relation", "evidence": []}]
    graph = verdict_preview.build(ledger, data)["argument_graph"]
    assert len(graph["nodes"]) == 2 and all(n["kind"] == "agent" for n in graph["nodes"])
    assert graph["edges"] == []
    declaration, = graph["edge_declarations"]
    assert declaration["declaration"] == finding["edges"][0] and declaration["binding"]["status"] == "invalid"


@pytest.mark.parametrize("missing", ["id", "at", "role", "reason", "key"])
def test_missing_node_fields_are_not_filled_with_display_defaults(prepared, missing):
    ledger, data = prepared
    original = data["findings"][0]["nodes"][0]
    del original[missing]
    graph = verdict_preview.build(ledger, data)["argument_graph"]
    declaration = graph["node_declarations"][0]
    assert declaration["binding"]["status"] == "invalid"
    assert missing not in declaration["declaration"]
    if missing != "id":
        assert missing not in declaration
    assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 1


def test_coverage_duplicates_missing_reason_and_unknown_finding_remain_unresolved(prepared):
    ledger, data = prepared
    data["coverage"] = [{"event": "dup", "finding": "F", "status": "explained", "reason": "first"},
                        {"event": "dup", "finding": "F", "status": "explained", "reason": "second"},
                        {"event": "missing-reason", "status": "not_repair"},
                        {"event": "other", "finding": "B,C", "status": "explained", "reason": "not split"},
                        {"event": "valid-shape", "finding": "F", "status": "explained", "reason": "not checked"}]
    graph = verdict_preview.build(ledger, data)["argument_graph"]
    assert len(graph["coverage"]) == 5
    assert [r["status"] for r in graph["coverage"]] == ["invalid"] * 4 + ["unresolved"]
    assert all(r["binding"]["status"] != "matched" for r in graph["coverage"])
    assert graph["coverage"][0]["declaration"] == data["coverage"][0]
    assert graph["coverage"][3]["finding"] == "B,C"


def test_remarks_never_become_nodes_bindings_or_verified_origins(prepared):
    ledger, data = prepared
    data["unknown"] = "agent-z wrote a hidden file"
    data["findings"][0]["counterevidence"] = ["not parsed as a historical read"]
    data["findings"][0]["nodes"][0]["binding"] = {"status": "confirmed", "semantic_checked": True}
    got = verdict_preview.build(ledger, data, meta={"verified": True, "document_sha256": "forged",
        "document_source": {"kind": "cached", "verified": True}, "nodes": [{"id": "injected"}]})
    graph = got["argument_graph"]
    assert len(graph["nodes"]) == 3 and len(graph["model_remarks"]) == 2
    assert graph["nodes"][0]["binding"]["status"] == "matched"
    assert graph["nodes"][0]["binding"]["semantic_checked"] is False
    assert got["document_source"]["verified"] is False
    assert got["authentication"]["status"] == "not_performed_by_preview"
    assert got["document_sha256"] != "forged"


def test_real_citation_and_mechanical_relation_are_not_causal_certification(prepared):
    ledger, data = prepared
    data["unknown"] = "force preview without accepting format"
    data["findings"][0]["edges"][1]["evidence"] = [raw_ref(ledger, "agent-c", "Read")]
    edge = verdict_preview.build(ledger, data)["argument_graph"]["edges"][1]
    assert edge["evidence"][0]["status"] == "ok"
    assert edge["binding"]["status"] == "not_observed"
    assert edge["binding"]["state_binding"] == "not_proven"
    assert edge["propagation"]["claim"] == data["findings"][0]["edges"][1]["claim"]
    assert edge["propagation"]["semantic_checked"] is False


@pytest.mark.parametrize("value", [datetime(2026, 1, 1, tzinfo=timezone.utc), float("nan"), float("inf"), {"not-json-set"}])
def test_non_json_safe_parse_values_fail_closed_preserve_raw_without_coercion(prepared, value):
    ledger, data = prepared
    data["target"]["at"] = value
    raw = "target:\n  at: 2026-01-01T00:00:00Z\n"
    got = verdict_preview.build(ledger, data, raw=raw)
    assert got["identity"]["bound"] is False and not got["original_schema_valid"]
    assert got["argument_graph"]["nodes"] == [] and got["original_document"] is None
    assert not got["original_document_available"] and got["document_sha256"] is None
    assert got["raw"] == raw and got["raw_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert got["schema_errors"]
    json.dumps(got, allow_nan=False)  # No datetime/NaN leak causes the HTTP response to fail.


def test_recursive_alias_and_nonstring_keys_are_not_silently_canonicalized(prepared):
    ledger, data = prepared
    data["unknown"] = {1: "integer key"}
    data["loop"] = data
    got = verdict_preview.build(ledger, data, raw="&a {loop: *a}")
    assert not got["identity"]["bound"] and not got["original_document_available"]
    assert any("recursive alias" in e for e in got["schema_errors"])
    assert any("non-string JSON key" in e for e in got["schema_errors"])
    json.dumps(got, allow_nan=False)


def test_position_only_finding_ids_cannot_collide_with_an_actual_model_id(prepared):
    ledger, data = prepared
    data["findings"].append(deepcopy(data["findings"][0]))
    other = deepcopy(data["findings"][0])
    other["id"] = "@preview:/findings/0"
    data["findings"].append(other)
    graph = verdict_preview.build(ledger, data)["argument_graph"]
    assert len({f["id"] for f in graph["findings"]}) == 3
    assert graph["findings"][2]["id"] == other["id"]
    assert all(n["binding"]["status"] == "matched" for n in graph["nodes"] if n["finding"] == other["id"])


def test_invalid_evidence_object_is_preserved_but_never_treated_as_a_real_ref(prepared):
    ledger, data = prepared
    invalid = {"ref": "raw:forged:L1:hash", "verified": True}
    data["findings"][0]["nodes"][0]["evidence"] = [invalid]
    graph = verdict_preview.build(ledger, data)["argument_graph"]
    evidence, = graph["nodes"][0]["evidence"]
    assert evidence["ref"] is None and evidence["status"] == "invalid"
    assert evidence["declaration"] == invalid
