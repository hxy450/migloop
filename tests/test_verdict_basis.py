"""Optional causal basis is model text plus separately resolved references, not truth certification."""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

from migloop import atoms, verdict
from tests.test_verdict import _pool


def basis(**changes: Any) -> dict[str, Any]:
    return {"expected": "  只放大数字段\n后缀保持基础字号  ", "actual": "  整串统一放大  ",
            "expected_evidence": ["  file:/proj/spec/pages/A.md@v1  "],
            "actual_evidence": ["file:/proj/entry/A.ets@v1"],
            "counterevidence": "  未核到修后设备结果；没有据此认证行为。\n", **changes}


def document(ledger: atoms.Ledger, *, role: str = "进入·错", with_basis: bool = True) -> dict[str, Any]:
    node = {"node": "agent:agent-c@v1", "role": role, "reason": "原始角色原因保持不变",
            "evidence": ["file:/proj/entry/A.ets@v1"]}
    if with_basis:
        node["basis"] = basis()
    return {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger), "root": "file:/proj/entry/A.ets@v1",
            "defects": [{"id": "A", "title": "问题甲", "nodes": [node], "edges": []}]}


def build(ledger: atoms.Ledger, data: dict[str, Any], **meta: Any) -> dict[str, Any]:
    return verdict.build(ledger, data, verdict.validate(data), meta)


def test_optional_basis_preserves_old_blocks_without_turning_advisory_into_parse_failure(tmp_path: Any) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger, with_basis=False)
    raw = json.dumps(data, ensure_ascii=False)
    parsed = verdict.load_block("```json\n" + raw + "\n```")
    assert parsed["errors"] == [] and parsed["data"] == data and parsed["raw"].strip() == raw
    result = build(ledger, parsed["data"])
    row = result["defects"][0]["nodes"][0]
    assert row["basis"] is None and row["basis_evidence_bad"] == 0
    assert row["ok"] and row["role"] == "进入·错" and row["checked"] == "not_checked"
    assert result["errors"] == [] and result["identity"]["bound"]
    assert [a["code"] for a in result["consistency"]["advisories"]] == ["missing_causal_basis"]
    assert "basis" not in data["defects"][0]["nodes"][0]


def test_basis_build_preserves_text_and_original_references_without_semantic_upgrade(tmp_path: Any) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger)
    snapshot = deepcopy(data)
    parsed = verdict.load_block("```json\n" + json.dumps(data, ensure_ascii=False) + "\n```")
    assert parsed["errors"] == [] and parsed["data"] == data
    result = build(ledger, data)
    row = result["defects"][0]["nodes"][0]
    model_basis = row["basis"]
    for key in ("expected", "actual", "counterevidence"):
        assert model_basis[key] == data["defects"][0]["nodes"][0]["basis"][key]
    for key in ("expected_evidence", "actual_evidence"):
        assert model_basis[key][0]["status"] == "ok"
        assert model_basis[key][0]["original_ref"] == data["defects"][0]["nodes"][0]["basis"][key][0]
    assert model_basis["source"] == "model" and model_basis["semantic_checked"] is False
    assert "checked" not in model_basis and row["checked"] == "not_checked"
    assert row["basis_evidence_bad"] == row["evidence_bad"] == 0
    assert result["consistency"]["advisories"] == [] and data == snapshot


def test_yaml_basis_roundtrip_preserves_model_text(tmp_path: Any) -> None:
    import yaml
    data = document(_pool(tmp_path))
    raw = yaml.safe_dump(data, allow_unicode=True)
    parsed = verdict.load_block("```yaml\n" + raw + "```")
    assert parsed["errors"] == [] and parsed["data"] == data


@pytest.mark.parametrize("key", ["expected", "actual", "counterevidence", "expected_evidence", "actual_evidence"])
def test_provided_basis_requires_every_field(tmp_path: Any, key: str) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger)
    del data["defects"][0]["nodes"][0]["basis"][key]
    assert any("basis" in error and key in error for error in verdict.validate(data))


@pytest.mark.parametrize("bad", [None, [], "claim", 1, True])
def test_basis_must_be_mapping_when_present(tmp_path: Any, bad: Any) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger)
    data["defects"][0]["nodes"][0]["basis"] = bad
    assert any("basis" in error for error in verdict.validate(data))


@pytest.mark.parametrize("key", ["expected", "actual", "counterevidence"])
@pytest.mark.parametrize("bad", [None, "", " \n ", [], 3, True])
def test_basis_sides_and_counterevidence_are_nonempty_strings(tmp_path: Any, key: str, bad: Any) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger)
    data["defects"][0]["nodes"][0]["basis"][key] = bad
    assert any("basis" in error and key in error for error in verdict.validate(data))


@pytest.mark.parametrize("key", ["expected_evidence", "actual_evidence"])
@pytest.mark.parametrize("bad", [None, [], "ref", [""], [" \n"], [1], [{"ref": "file:/proj/entry/A.ets@v1", "status": "ok"}]])
def test_basis_reference_lists_cannot_be_empty_or_contain_resolver_claims(tmp_path: Any, key: str, bad: Any) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger)
    data["defects"][0]["nodes"][0]["basis"][key] = bad
    assert any("basis" in error and key in error for error in verdict.validate(data))


@pytest.mark.parametrize("key", ["checked", "semantic_checked", "source", "validated", "extra"])
def test_model_cannot_supply_basis_verification_or_extra_fields(tmp_path: Any, key: str) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger)
    data["defects"][0]["nodes"][0]["basis"][key] = True
    parsed = verdict.load_block("```json\n" + json.dumps(data) + "\n```")
    assert parsed["data"] is None and any("basis" in error and key in error for error in parsed["errors"])


def test_basis_evidence_failures_are_separate_from_ordinary_evidence(tmp_path: Any) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger)
    raw_node = data["defects"][0]["nodes"][0]
    raw_node["basis"]["actual_evidence"] = ["file:/missing/A.ets@v1", "unlocated source prose"]
    result = build(ledger, data)
    row = result["defects"][0]["nodes"][0]
    assert result["errors"] == [] and row["ok"] and row["evidence_bad"] == 0
    assert row["basis_evidence_bad"] == 2
    assert [r["status"] for r in row["basis"]["actual_evidence"]] == ["invalid", "unparsed"]
    raw_node["evidence"] = ["ordinary unresolved source"]
    raw_node["basis"] = basis()
    row = build(ledger, data)["defects"][0]["nodes"][0]
    assert row["evidence_bad"] == 1 and row["basis_evidence_bad"] == 0


@pytest.mark.parametrize("mode", ["missing", "model_mismatch", "harness_mismatch", "trace_unbound"])
def test_unbound_basis_keeps_text_but_never_resolves_any_reference(tmp_path: Any, monkeypatch: Any, mode: str) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger)
    metadata = {}
    if mode == "missing":
        del data["ledger"]
    elif mode == "model_mismatch":
        data["ledger"] = "other-ledger"
    elif mode == "harness_mismatch":
        metadata["harness_identity"] = "other-ledger"
    else:
        metadata["trace_identity"] = {"bound": False}
    def prohibited(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("unbound report attempted to resolve a current-ledger coordinate")
    monkeypatch.setattr(verdict, "resolve_evidence", prohibited)
    monkeypatch.setattr(verdict, "resolve_node", prohibited)
    result = build(ledger, data, **metadata)
    row = result["defects"][0]["nodes"][0]
    assert not result["identity"]["bound"] and not row["ok"] and result["roles"] == {}
    assert row["basis"]["expected"] == basis()["expected"]
    assert all(ref["status"] == "not_checked" for key in ("expected_evidence", "actual_evidence") for ref in row["basis"][key])
    assert not result["consistency"]["checked"] and result["consistency"]["advisories"] == []


@pytest.mark.parametrize("role", list(verdict.RED))
def test_all_red_roles_without_basis_warn_but_keep_role_and_coordinate(tmp_path: Any, role: str) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger, role=role, with_basis=False)
    result = build(ledger, data)
    row = result["defects"][0]["nodes"][0]
    advice = result["defects"][0]["advisories"][0]
    assert row["ok"] and row["role"] == role and row["reason"] == data["defects"][0]["nodes"][0]["reason"]
    assert advice["code"] == "missing_causal_basis" and advice["level"] == "warning" and advice["defect"] == "A"
    assert result["errors"] == []


def test_invalid_red_coordinate_is_not_replaced_or_exempted_from_missing_basis(tmp_path: Any) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger, with_basis=False)
    data["defects"][0]["nodes"][0]["node"] = "agent:agent-c@v999"
    result = build(ledger, data)
    row = result["defects"][0]["nodes"][0]
    assert not row["ok"] and row["key"] is None and row["role"] == "进入·错"
    assert result["roles"] == {}
    assert [a["code"] for a in result["consistency"]["advisories"]] == ["missing_causal_basis"]


@pytest.mark.parametrize("role", list(verdict.ROLES))
def test_identical_trimmed_sides_warn_only_for_red_claims_and_do_not_change_text(tmp_path: Any, role: str) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger, role=role)
    raw = data["defects"][0]["nodes"][0]["basis"]
    raw.update(expected="  相同文字\n", actual="相同文字  ")
    result = build(ledger, data)
    row = result["defects"][0]["nodes"][0]
    assert row["basis"]["expected"] == raw["expected"] and row["basis"]["actual"] == raw["actual"]
    assert row["ok"] and row["role"] == role
    assert [a["code"] for a in result["consistency"]["advisories"]] == (["identical_causal_sides"] if role in verdict.RED else [])


def test_different_defects_do_not_share_basis_or_missing_basis_warnings(tmp_path: Any) -> None:
    ledger = _pool(tmp_path)
    data = document(ledger, with_basis=False)
    second = deepcopy(document(ledger)["defects"][0])
    second.update(id="B", title="独立问题乙")
    data["defects"].append(second)
    snapshot = deepcopy(data)
    result = build(ledger, data)
    first, second = result["defects"]
    assert first["advisories"][0]["code"] == "missing_causal_basis" and second["advisories"] == []
    assert first["nodes"][0]["basis"] is None and second["nodes"][0]["basis"]["source"] == "model"
    assert [a["defect"] for a in result["consistency"]["advisories"]] == ["A"]
    assert data == snapshot
