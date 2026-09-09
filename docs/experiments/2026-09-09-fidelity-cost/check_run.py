"""Read-only run inspection; the only write is a new check*.json beside run artifacts.

python check_run.py RUN_DIR CASE_DIR [--output check-again.json]
Counts prove schema/coordinates/recorded relations only, never assertion truth.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory_digest(root: Path) -> str:
    root = root.resolve(strict=True)
    entries = []
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Snapshot contains a link or escaped path: {path}")
        if path.is_file():
            entries.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                            "sha256": sha256(path)})
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshot_integrity(case_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    source = inventory_digest(Path(case["source"]) / "src" / "migloop")
    pool = inventory_digest(Path(case["pool"]))
    task = sha256(case_dir / "common-task.md")
    return {"source_unchanged": source == case["source_digest"], "pool_unchanged": pool == case["pool_digest"],
            "task_unchanged": task == case["common_task_sha256"], "source_digest": source, "pool_digest": pool}


def normalized_payload(case: dict[str, Any], run_dir: Path) -> tuple[dict[str, Any], str]:
    """Use this case's frozen implementation and pool, never already-loaded live modules."""
    source = (Path(case["source"]) / "src").resolve(strict=True)
    if not (source / "migloop" / "probe.py").is_file():
        raise ValueError(f"Frozen source does not contain migloop/probe.py: {source}")
    existing = sys.modules.get("migloop")
    if existing is not None and not Path(existing.__file__).resolve().is_relative_to(source):
        raise RuntimeError("migloop was imported from another source; run the checker in a fresh process")
    old_path, old_bytecode = list(sys.path), sys.dont_write_bytecode
    old_pool = os.environ.get("MIGLOOP_FROZEN_POOL")
    sys.path.insert(0, str(source))
    sys.dont_write_bytecode = True
    os.environ["MIGLOOP_FROZEN_POOL"] = str(Path(case["pool"]).resolve())
    try:
        service, atoms, probe = [importlib.import_module("migloop." + name) for name in ("service", "atoms", "probe")]
        for module in (service, atoms, probe):
            if not Path(module.__file__).resolve().is_relative_to(source):
                raise RuntimeError("A migloop module was loaded outside the frozen source")
        ledger = service.session_ledger(case["current_root"])
        payload = probe_with_coverage(service, probe, ledger, run_dir, case["current_root"],
                                      coverage_module_available=(source / "migloop" / "coverage.py").is_file())
        return payload, atoms.ledger_identity(ledger)
    finally:
        sys.path[:] = old_path
        sys.dont_write_bytecode = old_bytecode
        if old_pool is None:
            os.environ.pop("MIGLOOP_FROZEN_POOL", None)
        else:
            os.environ["MIGLOOP_FROZEN_POOL"] = old_pool


def probe_with_coverage(service: Any, probe: Any, ledger: Any, run_dir: Path, root: str,
                        *, coverage_module_available: bool) -> dict[str, Any]:
    """New frozen sources reconcile their own manifest; old sources are explicitly unavailable.

    Do not import live coverage code into an old snapshot or retry an internal TypeError
    as if it were an old function signature.
    """
    parameter = inspect.signature(probe.probe_payload).parameters.get("chain_payload")
    accepts_chains = parameter is not None and parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    available = accepts_chains and coverage_module_available and callable(getattr(service, "fixchain_payload", None))
    kwargs = {"chain_payload": service.fixchain_payload(root)} if available else {}
    payload = probe.probe_payload(ledger, str(run_dir), **kwargs)
    payload["_check_capabilities"] = {
        "chain_payload_parameter": accepts_chains, "coverage_module": coverage_module_available,
        "coverage_requested": available,
        "reason": None if available else "Frozen source does not provide the coverage-capable probe/service/module contract.",
    }
    return payload


def summarize_coverage(payload: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    """Accounting is not discovery completeness, semantic correctness or confirmed repair."""
    manifest, reconciliation = payload.get("repair_manifest"), payload.get("coverage")
    available = isinstance(manifest, dict) and isinstance(reconciliation, dict)
    meaning = ("Complete means every registered version/candidate has one valid explicit declaration. "
               "Unresolved counts as accounted but not resolved. Resolved counts explained/not_repair declarations, "
               "not verified fixes. Schema validity does not imply accounting completeness or semantic correctness. "
               "The manifest does not establish that every real repair or semantic hunk was found.")
    if not available:
        return {"available": False, "status": "unavailable", "complete": False,
                "identity_bound": identity.get("bound") is True, "counts": None,
                "registered_versions": None, "registered_candidates": None,
                "unaccounted_versions": None, "unaccounted_candidates": None,
                "semantic_checked": False, "evidence_checked": False, "interpretation": meaning,
                "reason": (payload.get("_check_capabilities") or {}).get("reason")
                          or "No target manifest/reconciliation was returned by this frozen source."}
    versions = [item["node"] for item in manifest.get("items") or []]
    candidates = [item["id"] for item in manifest.get("candidates") or []]
    expected = versions + candidates
    rows = reconciliation.get("rows") or []
    occurrences = Counter(row.get("canonical_target") for row in rows)
    # A duplicate or invalid declaration is not accounted even if its target occurs in the report.
    accounted_rows = [row for row in rows if row.get("valid") is True
                      and row.get("canonical_target") in expected
                      and occurrences[row["canonical_target"]] == 1]
    accounted = {row["canonical_target"] for row in accounted_rows}
    unresolved = [row["canonical_target"] for row in accounted_rows if row.get("status") == "unresolved"]
    resolved = [row["canonical_target"] for row in accounted_rows if row.get("status") in ("explained", "not_repair")]
    identity_bound = (identity.get("bound") is True and reconciliation.get("identity_bound") is True
                      and (payload.get("trace_identity") or {}).get("bound") is not False)
    complete = (reconciliation.get("complete") is True and identity_bound
                and not reconciliation.get("errors") and not manifest.get("errors") and len(accounted) == len(expected))
    status = "unbound" if not identity_bound else "complete" if complete else reconciliation.get("status") or "incomplete"
    if status == "complete" and not complete:
        status = "incomplete"
    missing_versions = [node for node in versions if not occurrences[node]]
    missing_candidates = [node for node in candidates if not occurrences[node]]
    unaccounted_versions = [node for node in versions if node not in accounted]
    unaccounted_candidates = [node for node in candidates if node not in accounted]
    return {"available": True, "status": status, "complete": complete, "identity_bound": identity_bound,
            "scope": manifest.get("scope"), "registered_versions": versions, "registered_candidates": candidates,
            "accounted_targets": [node for node in expected if node in accounted],
            "resolved_targets": resolved, "unresolved_targets": unresolved,
            "missing_versions": missing_versions, "missing_candidates": missing_candidates,
            "unaccounted_versions": unaccounted_versions, "unaccounted_candidates": unaccounted_candidates,
            "out_of_scope_declarations": reconciliation.get("out_of_scope") or [],
            "counts": {"expected": len(expected), "registered_versions": len(versions), "registered_candidates": len(candidates),
                       "provided": (reconciliation.get("counts") or {}).get("provided", len(rows)),
                       "accounted": len(accounted), "resolved": len(resolved), "unresolved": len(unresolved),
                       "missing_versions": len(missing_versions), "missing_candidates": len(missing_candidates),
                       "unaccounted_versions": len(unaccounted_versions), "unaccounted_candidates": len(unaccounted_candidates)},
            "semantic_checked": False, "evidence_checked": False, "interpretation": meaning,
            "reconciliation": reconciliation}


def summarize_payload(payload: dict[str, Any], required: bool | None = None) -> dict[str, Any]:
    structured = payload.get("structured")
    present = isinstance(structured, dict)
    errors = list((structured or {}).get("errors") or [])
    schema_ok = not errors if present else False if required else None
    defects = (structured or {}).get("defects") or []
    nodes = [node for defect in defects for node in defect.get("nodes") or []]
    valid = [node for node in nodes if node.get("ok") is True and node.get("kind") in ("file", "agent")
             and node.get("key") and isinstance(node.get("v"), int) and node["v"] > 0]
    evidence = [ref for defect in defects for ref in (defect.get("repair") or {}).get("evidence") or []]
    evidence += [ref for node in nodes for ref in node.get("evidence") or []]
    edges = [edge for defect in defects for edge in defect.get("edges") or []]

    def edge_counts(implicit: bool) -> dict[str, Any]:
        rows = [edge for edge in edges if bool(edge.get("implicit")) == implicit]
        statuses = Counter(edge.get("status") or "not_checked" for edge in rows)
        return {"total": len(rows), "with_ledger_relation": statuses["true"], "status_counts": dict(statuses),
                "claimed_relation_counts": dict(Counter(edge.get("claimed") or "unspecified" for edge in rows))}

    trajectory = payload.get("trajectory") or {}
    visits, steps = trajectory.get("visits") or [], payload.get("steps") or []
    statuses = Counter(visit.get("status") or "unspecified" for visit in visits)
    timing_unknown = [visit for visit in visits if any(word in str(visit.get("note") or "")
                      for word in ("时序分辨率不足", "先后未确认"))]
    identity = dict((structured or {}).get("identity") or {})
    identity.setdefault("bound", False)
    identity.setdefault("status", "missing")
    # Serialization is a server-payload check, not a browser/visual check.
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return {
        "schema_required": required, "schema_present": present, "schema_ok": schema_ok,
        "schema_status": "valid" if schema_ok is True else "invalid_or_missing" if schema_ok is False else "not_applicable",
        "schema_errors": errors, "identity": identity,
        "trace_identity": payload.get("trace_identity"),
        "repair_manifest": payload.get("repair_manifest"),
        "coverage": summarize_coverage(payload, identity),
        "normalizer_capabilities": payload.get("_check_capabilities"),
        "defect_count": len(defects) if present and not errors else None,
        "defect_ids": [defect.get("id") for defect in defects],
        "nodes": {"total": len(nodes), "exact_valid": len(valid),
                  "unique_exact_coordinates": len({(n["kind"], n["key"], n["v"]) for n in valid}),
                  "scope": "defect-scoped role rows; shared nodes count once per declared defect row",
                  "invalid": [{"spec": n.get("spec"), "defect": n.get("defect"), "diag": n.get("diag")}
                              for n in nodes if n not in valid]},
        "evidence": {"total": len(evidence), "locatable": sum(e.get("status") in ("ok", "drifted") for e in evidence),
                     "status_counts": dict(Counter(e.get("status") or "unspecified" for e in evidence)),
                     "scope": "role evidence and repair evidence; repeated citations counted as declared",
                     "claim_support_checked": False},
        "edges": {"model_declared": edge_counts(False), "automatic_adjacency_checks": edge_counts(True),
                  "meaning": "true confirms a ledger write/read/dispatch relation, not defect causality"},
        "calls": {"total_records": len(steps),
                  "returned_without_error_flag": sum(s.get("result_present") is True and s.get("ok") is True for s in steps),
                  "returned_with_error_flag": sum(s.get("result_present") is True and s.get("ok") is False for s in steps),
                  "pending": sum(s.get("result_present") is False for s in steps),
                  "unknown_return_state": sum(s.get("result_present") is None for s in steps),
                  "by_tool": dict(Counter(s.get("tool") or "unspecified" for s in steps)),
                  "by_provenance": dict(Counter((s.get("provenance") or {}).get("format") or "legacy_metrics" for s in steps)),
                  "scope": "normalized records, not successful node visits; outer exec and nested MCP remain distinct"},
        "visits": {"total": len(visits), "opened": statuses["opened"], "error": statuses["error"],
                   "rejected": statuses["rejected"], "pending": statuses["pending"], "unverified": statuses["unverified"],
                   "timing_unknown": len(timing_unknown), "timing_unknown_steps": [v.get("step") for v in timing_unknown],
                   "timing_note": "timing_unknown overlaps visit status; successful return does not prove via timing",
                   "verification": trajectory.get("verification"), "declared_transitions": len(trajectory.get("transitions") or [])},
        "ui_payload_check": {"probe_payload_created": True, "json_serializable": True, "browser_render_checked": False},
        "assertion_truth_checked": False,
        "interpretation": ("Structural, registered-manifest accounting and traceability inspection only. "
                           "Schema validity is not completeness or semantic correctness. No reason validation and no accuracy score."),
    }


def check_run(run_dir: Path, case_dir: Path) -> dict[str, Any]:
    run_dir, case_dir = run_dir.resolve(strict=True), case_dir.resolve(strict=True)
    case = read_json(case_dir / "case.json")
    if case.get("schema") != "migloop-pair-case/1" or case.get("read_only_snapshot") is not True:
        raise ValueError("A read-only migloop-pair-case/1 snapshot is required")
    if not run_dir.is_relative_to(case_dir / "runs"):
        raise ValueError("run_dir must belong to case_dir/runs")
    pool = Path(case["pool"]).resolve(strict=True)
    current = Path(case["current_root"]).resolve(strict=True)
    if not pool.is_relative_to(case_dir) or current.parent != pool:
        raise ValueError("Case pool/root is outside the declared frozen case")
    result: dict[str, Any] = {"schema": "migloop-run-check/1", "checked_at": datetime.now(timezone.utc).isoformat(),
                              "run_dir": str(run_dir), "case_dir": str(case_dir), "source": case["source"],
                              "source_code_id": case.get("source_code_id"), "normalization_succeeded": False,
                              "assertion_truth_checked": False}
    started = time.perf_counter()
    try:
        integrity = snapshot_integrity(case_dir, case)
        result["snapshot_integrity"] = integrity
        if not all(integrity[key] for key in ("source_unchanged", "pool_unchanged", "task_unchanged")):
            raise ValueError("Frozen snapshot integrity changed; current data was not normalized")
        verdict_path = run_dir / "verdict.json"
        saved = read_json(verdict_path) if verdict_path.exists() else {}
        payload, current_identity = normalized_payload(case, run_dir)
        result.update(summarize_payload(payload, saved.get("required")))
        result.update(normalization_succeeded=True, frozen_ledger_identity=current_identity)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, ImportError, AttributeError) as error:
        result["check_error"] = {"type": type(error).__name__, "message": str(error)}
    result["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    return result


def write_check(run_dir: Path, result: dict[str, Any], output: Path | None = None) -> Path:
    run_dir = run_dir.resolve(strict=True)
    destination = output if output is not None else Path("check.json")
    destination = (run_dir / destination).resolve() if not destination.is_absolute() else destination.resolve()
    if destination.parent != run_dir or not destination.name.startswith("check") or destination.suffix != ".json":
        raise ValueError("Output must be a new check*.json directly inside run_dir")
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--output", type=Path, help="New check*.json name (default: check.json; never overwrite)")
    args = parser.parse_args(argv)
    try:
        result = check_run(args.run_dir, args.case_dir)
        output = write_check(args.run_dir, result, args.output)
    except (ValueError, OSError) as error:
        parser.exit(2, f"check_run: {error}\n")
    print(json.dumps({"check_file": str(output), "normalization_succeeded": result["normalization_succeeded"],
                      "schema_ok": result.get("schema_ok"), "identity_bound": (result.get("identity") or {}).get("bound"),
                      "coverage_available": (result.get("coverage") or {}).get("available"),
                      "coverage_complete": (result.get("coverage") or {}).get("complete"),
                      "assertion_truth_checked": False}, ensure_ascii=False))
    return 0 if result["normalization_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
