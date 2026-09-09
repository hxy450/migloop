"""Run checks measure structural validity without asserting factual accuracy."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "docs/experiments/2026-09-09-fidelity-cost/check_run.py"
spec = importlib.util.spec_from_file_location("run_check", SCRIPT)
assert spec and spec.loader
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def payload() -> dict[str, Any]:
    return {"structured": {"errors": [], "identity": {"bound": True, "status": "matched"}, "defects": [{
        "id": "A", "repair": {"evidence": [{"status": "ok"}]},
        "nodes": [{"spec": "file:A@v1", "kind": "file", "key": "/p/A", "v": 1, "ok": True,
                   "checks": [{"claim": "model says true", "result": "true"}], "checked": "not_checked",
                   "evidence": [{"status": "ok"}, {"status": "drifted"}, {"status": "missing"}]},
                  {"spec": "file:bad@v99", "key": None, "v": 99, "ok": False, "diag": "missing",
                   "evidence": [{"status": "invalid"}]}],
        "edges": [{"status": "true", "implicit": False, "claimed": "写"},
                  {"status": "false", "implicit": False, "claimed": "读"},
                  {"status": "true", "implicit": True, "claimed": None}]}]},
        "steps": [{"tool": "file", "result_present": True, "ok": True},
                  {"tool": "agent", "result_present": True, "ok": False},
                  {"tool": "file", "result_present": False, "ok": False},
                  {"tool": "file", "result_present": None, "ok": True}],
        "trajectory": {"verification": "returned_coordinates", "transitions": [{}], "visits": [
            {"step": 1, "status": "opened", "note": "时序分辨率不足,先后未确认"},
            {"step": 2, "status": "error"}, {"step": 3, "status": "rejected"},
            {"step": 4, "status": "pending"}, {"step": 5, "status": "unverified"}]}}


def test_counts_separate_schema_nodes_evidence_edges_and_runtime_states() -> None:
    result = check.summarize_payload(payload(), required=True)
    assert result["schema_ok"] and result["identity"]["bound"] and result["defect_count"] == 1
    assert (result["nodes"]["exact_valid"], result["nodes"]["total"]) == (1, 2)
    assert (result["evidence"]["locatable"], result["evidence"]["total"]) == (3, 5)
    assert result["evidence"]["status_counts"]["drifted"] == 1
    assert result["edges"]["model_declared"]["total"] == 2
    assert result["edges"]["model_declared"]["with_ledger_relation"] == 1
    assert result["edges"]["automatic_adjacency_checks"]["with_ledger_relation"] == 1
    assert result["calls"]["pending"] == result["calls"]["unknown_return_state"] == 1
    assert result["visits"]["opened"] == result["visits"]["timing_unknown"] == 1
    assert result["visits"]["error"] == result["visits"]["rejected"] == result["visits"]["pending"] == 1
    assert not result["assertion_truth_checked"] and not result["evidence"]["claim_support_checked"]
    assert not result["ui_payload_check"]["browser_render_checked"] and "accuracy" not in result


@pytest.mark.parametrize("required,expected", [(False, None), (None, None), (True, False)])
def test_missing_yaml_is_not_a_raw_arm_failure(required: bool | None, expected: bool | None) -> None:
    result = check.summarize_payload({"structured": None, "steps": [], "trajectory": None}, required)
    assert result["schema_ok"] is expected
    assert result["identity"]["bound"] is False and result["defect_count"] is None


def test_schema_validity_does_not_override_unbound_identity() -> None:
    value = payload()
    value["structured"]["identity"] = {"bound": False, "status": "mismatch"}
    for node in value["structured"]["defects"][0]["nodes"]:
        node.update(ok=False, key=None, diag="unbound")
    result = check.summarize_payload(value, True)
    assert result["schema_ok"] is True and result["identity"]["bound"] is False
    assert result["nodes"]["exact_valid"] == 0 and result["nodes"]["total"] == 2


def frozen_case(tmp_path: Path) -> tuple[Path, Path]:
    case_dir = tmp_path / "case"
    run_dir = case_dir / "runs/tools/rep1"
    run_dir.mkdir(parents=True)
    pool = case_dir / "pool"
    pool.mkdir()
    current = pool / "root.jsonl"
    current.write_text('{}\n', encoding="utf-8")
    source = tmp_path / "source"
    package = source / "src/migloop"
    package.mkdir(parents=True)
    (package / "probe.py").write_text("# synthetic snapshot\n", encoding="utf-8")
    (case_dir / "common-task.md").write_text("task", encoding="utf-8")
    case = {"schema": "migloop-pair-case/1", "read_only_snapshot": True, "source": str(source),
            "pool": str(pool), "current_root": str(current), "roots": [str(current)], "source_digest": check.inventory_digest(package),
            "pool_digest": check.inventory_digest(pool), "common_task_sha256": check.sha256(case_dir / "common-task.md")}
    (case_dir / "case.json").write_text(json.dumps(case), encoding="utf-8")
    return case_dir, run_dir


def test_changed_snapshot_is_reported_without_normalizing_new_data(tmp_path: Path, monkeypatch: Any) -> None:
    case_dir, run_dir = frozen_case(tmp_path)
    (case_dir / "pool/root.jsonl").write_text('{"changed":true}\n', encoding="utf-8")

    def forbidden(*args: Any) -> None:
        raise AssertionError("Changed pool must not be normalized")

    monkeypatch.setattr(check, "normalized_payload", forbidden)
    result = check.check_run(run_dir, case_dir)
    assert result["normalization_succeeded"] is False
    assert result["snapshot_integrity"]["pool_unchanged"] is False
    assert "integrity changed" in result["check_error"]["message"]


def test_checker_never_overwrites_existing_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    original = run_dir / "result.json"
    original.write_text('{"original":true}', encoding="utf-8")
    result = {"normalization_succeeded": True}
    destination = check.write_check(run_dir, result)
    assert json.loads(destination.read_text(encoding="utf-8")) == result
    with pytest.raises(FileExistsError):
        check.write_check(run_dir, {"replacement": True})
    for path in (Path("result.json"), Path("../check.json")):
        with pytest.raises(ValueError):
            check.write_check(run_dir, result, path)
    assert original.read_text(encoding="utf-8") == '{"original":true}'


def test_loading_another_source_requires_a_fresh_process(tmp_path: Path) -> None:
    import migloop  # noqa: F401 - intentionally populate the live module cache

    case_dir, run_dir = frozen_case(tmp_path)
    case = check.read_json(case_dir / "case.json")
    with pytest.raises(RuntimeError, match="fresh process"):
        check.normalized_payload(case, run_dir)


def covered_payload(*, declarations: list[dict[str, Any]] | None = None,
                    candidate: bool = True) -> dict[str, Any]:
    from migloop import coverage
    from tests.test_repair_coverage import PATH, candidate_action, declaration, splash_ledger

    ledger, chains = splash_ledger()
    if candidate:
        candidate_action(ledger, 100, touch=True)
    manifest = coverage.manifest(ledger, chains, PATH)
    if declarations is None:
        declarations = [declaration(52), declaration(53, "not_repair"), declaration(54, "unresolved")]
        declarations += [{"candidate": item["id"], "status": "unresolved", "defects": [],
                          "reason": "未确认这个候选动作是否真实修复", "evidence": []} for item in manifest["candidates"]]
    value = payload()
    value["repair_manifest"] = manifest
    value["coverage"] = coverage.reconcile(ledger, manifest, declarations, [{"id": "A"}], identity_bound=True)
    return value


def test_registry_accounts_unresolved_without_claiming_semantic_resolution() -> None:
    value = covered_payload()
    result = check.summarize_payload(value, required=True)
    report = result["coverage"]
    assert result["schema_ok"] and report["available"] and report["complete"]
    assert report["counts"]["registered_versions"] == 3 and report["counts"]["registered_candidates"] == 1
    assert report["counts"]["accounted"] == 4
    assert report["counts"]["unresolved"] == report["counts"]["resolved"] == 2
    assert set(report["unresolved_targets"]).isdisjoint(report["resolved_targets"])
    assert report["unaccounted_versions"] == report["unaccounted_candidates"] == []
    assert result["repair_manifest"] == value["repair_manifest"]
    assert report["reconciliation"] == value["coverage"]
    assert report["semantic_checked"] is False and report["evidence_checked"] is False
    assert "not verified fixes" in report["interpretation"]


def test_schema_valid_report_can_omit_registered_versions_and_candidates() -> None:
    from tests.test_repair_coverage import PATH, declaration

    result = check.summarize_payload(covered_payload(declarations=[declaration(54)]), True)
    report = result["coverage"]
    assert result["schema_ok"] is True and report["complete"] is False
    assert report["status"] == "incomplete" and report["counts"]["accounted"] == 1
    assert report["missing_versions"] == report["unaccounted_versions"] == [f"file:{PATH}@v52", f"file:{PATH}@v53"]
    assert report["missing_candidates"] == report["unaccounted_candidates"] == report["registered_candidates"]


def test_duplicate_and_invalid_rows_are_distinct_from_absent_and_out_of_scope_rows() -> None:
    from tests.test_repair_coverage import PATH, declaration

    rows = [declaration(52), declaration(52), declaration(53, reason=""), declaration(1)]
    report = check.summarize_payload(covered_payload(declarations=rows), True)["coverage"]
    assert report["status"] == "invalid" and report["complete"] is False
    assert report["counts"]["accounted"] == report["counts"]["resolved"] == 0
    assert report["missing_versions"] == [f"file:{PATH}@v54"]
    assert report["unaccounted_versions"] == report["registered_versions"]
    assert len(report["out_of_scope_declarations"]) == 1
    assert report["reconciliation"]["duplicates"] and report["reconciliation"]["empty_reason"]


@pytest.mark.parametrize("bound", [False, None])
def test_unbound_identity_cannot_be_complete_even_with_stale_complete_payload(bound: bool | None) -> None:
    value = covered_payload()
    value["structured"]["identity"]["bound"] = bound
    assert value["coverage"]["complete"] is True
    report = check.summarize_payload(value, True)["coverage"]
    assert report["complete"] is False and report["identity_bound"] is False and report["status"] == "unbound"
    assert report["counts"]["accounted"] == 4  # Counts declarations, not identity certification.


def test_explicit_trace_identity_conflict_also_blocks_completion() -> None:
    value = covered_payload()
    value["trace_identity"] = {"bound": False, "status": "mismatch"}
    result = check.summarize_payload(value, True)
    assert result["coverage"]["complete"] is False
    assert result["coverage"]["status"] == "unbound"
    assert result["trace_identity"] == value["trace_identity"]


def test_old_payload_has_unknown_coverage_not_an_empty_complete_registry() -> None:
    report = check.summarize_payload(payload(), True)["coverage"]
    assert report["available"] is False and report["complete"] is False
    assert report["status"] == "unavailable" and report["counts"] is None
    assert report["registered_versions"] is None and report["unaccounted_candidates"] is None


def test_new_probe_receives_frozen_chain_payload_for_manifest_reconciliation() -> None:
    events = []
    ledger, chains = object(), {"chains": [{"fix_versions": [1, 3]}]}

    def chain_payload(root: str) -> dict[str, Any]:
        events.append(("chains", root))
        return chains

    def new_probe(actual: Any, run: str, *, chain_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        assert actual is ledger and chain_payload is chains
        events.append(("probe", run))
        return payload()

    value = check.probe_with_coverage(SimpleNamespace(fixchain_payload=chain_payload),
                                      SimpleNamespace(probe_payload=new_probe), ledger, Path("run"), "frozen-root",
                                      coverage_module_available=True)
    assert events == [("chains", "frozen-root"), ("probe", "run")]
    assert value["_check_capabilities"]["coverage_requested"] is True


@pytest.mark.parametrize("module_available", [False, True])
def test_old_probe_without_parameter_is_called_without_chains(module_available: bool) -> None:
    def forbidden(*args: Any) -> None:
        raise AssertionError("Do not build an unsupported chain payload")

    value = check.probe_with_coverage(SimpleNamespace(fixchain_payload=forbidden),
                                      SimpleNamespace(probe_payload=lambda ledger, run: payload()),
                                      object(), Path("run"), "frozen-root", coverage_module_available=module_available)
    assert value["_check_capabilities"]["chain_payload_parameter"] is False
    assert value["_check_capabilities"]["coverage_requested"] is False
    assert check.summarize_payload(value, True)["coverage"]["available"] is False


def test_missing_frozen_coverage_module_does_not_import_current_implementation() -> None:
    def forbidden(*args: Any) -> None:
        raise AssertionError("Frozen source lacks coverage; do not request it")

    def new_probe(ledger: Any, run: str, chain_payload: Any = None) -> dict[str, Any]:
        assert chain_payload is None
        return payload()

    value = check.probe_with_coverage(SimpleNamespace(fixchain_payload=forbidden),
                                      SimpleNamespace(probe_payload=new_probe), object(), Path("run"), "frozen-root",
                                      coverage_module_available=False)
    assert value["_check_capabilities"]["chain_payload_parameter"] is True
    assert value["_check_capabilities"]["coverage_requested"] is False


def test_new_probe_internal_typeerror_is_not_retried_as_legacy_signature() -> None:
    attempts = []

    def broken_probe(ledger: Any, run: str, chain_payload: Any = None) -> dict[str, Any]:
        attempts.append(chain_payload)
        raise TypeError("internal bug")

    with pytest.raises(TypeError, match="internal bug"):
        check.probe_with_coverage(SimpleNamespace(fixchain_payload=lambda root: {}),
                                  SimpleNamespace(probe_payload=broken_probe), object(), Path("run"), "frozen-root",
                                  coverage_module_available=True)
    assert attempts == [{}]


def variant_case(tmp_path: Path, parent: Path, name: str = "variant") -> tuple[Path, Path]:
    case_dir = tmp_path / name
    run_dir = case_dir / "runs/tools/rep1"
    run_dir.mkdir(parents=True)
    document = check.read_json(parent / "case.json")
    document["parent_case"] = {"case_dir": str(parent), "case_sha256": check.sha256(parent / "case.json")}
    (case_dir / "common-task.md").write_bytes((parent / "common-task.md").read_bytes())
    (case_dir / "case.json").write_text(json.dumps(document), encoding="utf-8")
    return case_dir, run_dir


def replace_case(case_dir: Path, **fields: Any) -> dict[str, Any]:
    document = {**check.read_json(case_dir / "case.json"), **fields}
    (case_dir / "case.json").write_text(json.dumps(document), encoding="utf-8")
    return document


def refresh_parent_hash(child: Path, parent: Path) -> dict[str, Any]:
    return replace_case(child, parent_case={"case_dir": str(parent), "case_sha256": check.sha256(parent / "case.json")})


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_owned_pool_and_hash_verified_variant_chains_preserve_integrity_checks(tmp_path: Path, monkeypatch: Any, depth: int) -> None:
    owner, run_dir = frozen_case(tmp_path)
    case_dir = owner
    for number in range(depth):
        case_dir, run_dir = variant_case(tmp_path, case_dir, "variant-" + str(number))
    calls = []

    def normalize(case: dict[str, Any], run: Path) -> tuple[dict[str, Any], str]:
        calls.append((case["pool"], run))
        return payload(), "frozen-identity"

    monkeypatch.setattr(check, "normalized_payload", normalize)
    result = check.check_run(run_dir, case_dir)
    assert result["normalization_succeeded"] is True
    assert all(result["snapshot_integrity"][field] for field in ("source_unchanged", "pool_unchanged", "task_unchanged"))
    authorization = result["pool_authorization"]
    assert authorization["shared"] is bool(depth)
    assert authorization["owner_case_dir"] == str(owner.resolve())
    assert len(authorization["parent_chain"]) == depth
    assert calls == [(str(owner / "pool"), run_dir.resolve())]


@pytest.mark.parametrize("tamper_parent_file", [False, True])
def test_shared_pool_rejects_tampered_parent_file_or_recorded_hash(tmp_path: Path, tamper_parent_file: bool) -> None:
    parent, _ = frozen_case(tmp_path)
    child, run = variant_case(tmp_path, parent)
    if tamper_parent_file:
        replace_case(parent, changed="parent contents changed after linking")
    else:
        replace_case(child, parent_case={"case_dir": str(parent), "case_sha256": "0" * 64})
    with pytest.raises(ValueError, match="SHA-256"):
        check.check_run(run, child)
    assert not (run / "check.json").exists()


def test_parent_hash_alone_does_not_authorize_an_unrelated_pool(tmp_path: Path) -> None:
    parent, _ = frozen_case(tmp_path)
    child, run = variant_case(tmp_path, parent)
    unrelated, _ = frozen_case(tmp_path / "unrelated")
    refresh_parent_hash(child, unrelated)
    with pytest.raises(ValueError, match="pool does not match"):
        check.check_run(run, child)


def test_shared_pool_requires_same_digest_in_parent_and_child(tmp_path: Path) -> None:
    parent, _ = frozen_case(tmp_path)
    child, run = variant_case(tmp_path, parent)
    replace_case(parent, pool_digest="0" * 64)
    refresh_parent_hash(child, parent)
    with pytest.raises(ValueError, match="pool_digest does not match"):
        check.check_run(run, child)


@pytest.mark.parametrize("cut_at", ["child", "intermediate"])
def test_external_pool_without_a_complete_explicit_sharing_chain_is_rejected(tmp_path: Path, cut_at: str) -> None:
    parent, _ = frozen_case(tmp_path)
    intermediate, _ = variant_case(tmp_path, parent, "intermediate")
    child, run = variant_case(tmp_path, intermediate, "child")
    replace_case(child if cut_at == "child" else intermediate, parent_case=None)
    if cut_at == "intermediate":
        refresh_parent_hash(child, intermediate)
    with pytest.raises(ValueError, match="explicit parent_case"):
        check.check_run(run, child)


@pytest.mark.parametrize("which", ["current_root", "roots", "parent_roots"])
def test_all_roots_remain_inside_the_declared_pool_even_for_variants(tmp_path: Path, which: str) -> None:
    parent, _ = frozen_case(tmp_path)
    child, run = variant_case(tmp_path, parent)
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    if which == "parent_roots":
        replace_case(parent, roots=[str(outside)])
        refresh_parent_hash(child, parent)
    else:
        replace_case(child, **{which: str(outside) if which == "current_root" else [str(outside)]})
    with pytest.raises(ValueError, match="all roots must be files directly inside"):
        check.check_run(run, child)


def test_shared_pool_content_tampering_still_blocks_normalization(tmp_path: Path, monkeypatch: Any) -> None:
    parent, _ = frozen_case(tmp_path)
    child, run = variant_case(tmp_path, parent)
    (parent / "pool/root.jsonl").write_text('{"tampered":true}\n', encoding="utf-8")

    def forbidden(*args: Any) -> None:
        raise AssertionError("A changed shared pool must not be normalized")

    monkeypatch.setattr(check, "normalized_payload", forbidden)
    result = check.check_run(run, child)
    assert result["pool_authorization"]["shared"] is True
    assert result["snapshot_integrity"]["pool_unchanged"] is False
    assert result["normalization_succeeded"] is False
    assert "integrity changed" in result["check_error"]["message"]
