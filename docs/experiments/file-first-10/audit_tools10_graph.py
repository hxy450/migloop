"""Read-only strict/partial production graph audit of a frozen tools package.

No model calls, report repair, browser inspection or semantic grading. Each pool
gets an isolated worker importing only the package's frozen production code.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def read(path):
    return Path(path).read_text(encoding="utf-8")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, data):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def inventory(base):
    return {p.relative_to(base).as_posix(): sha(p)
            for p in sorted(base.rglob("*")) if p.is_file()}


def protected(base, cases):
    names = [base / name for name in ("manifest.json", "code-manifest.json")]
    for case in cases:
        for rep in (1, 2):
            directory = base / "runs" / case["id"] / f"rep{rep}"
            names.extend(directory / name for name in ("report.md", "verdict.json", "metrics.json",
                                                         "query-trace.json", "transcript.jsonl"))
    return {str(path): sha(path) for path in names}


def worker(base, out, ids):
    manifest = json.loads(read(base / "manifest.json"))
    cases = [case for case in manifest["cases"] if case["id"] in ids]
    assert {case["id"] for case in cases} == set(ids)
    assert manifest["repetitions"] == 2
    code = base / "code" / "src"
    code_manifest = json.loads(read(base / "code-manifest.json"))
    package = code / "migloop"
    before_code = inventory(package)
    expected = {row["path"]: row["sha256"] for row in code_manifest["entries"]}
    assert before_code == expected, "Frozen package contents differ"
    before = protected(base, cases)
    settings = [json.loads(read(base / "settings" / (case["id"] + ".json"))) for case in cases]
    environments = [s["mcp_servers"]["migloop"]["env"] for s in settings]
    assert len({s["MIGLOOP_FROZEN_POOL"] for s in environments}) == 1
    pools = {Path(case["pool"]).resolve() for case in cases}
    assert len(pools) == 1
    pool = pools.pop()
    before_pool = inventory(pool)
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(environments[0])
    os.environ["MIGLOOP_RUNS"] = str(base / "runs")
    sys.path.insert(0, str(code))
    from migloop import probe, service

    ledger = service.session_ledger(environments[0]["MIGLOOP_FROZEN_ANCHOR"])
    rows = []
    for case in cases:
        for rep in (1, 2):
            run = base / "runs" / case["id"] / f"rep{rep}"
            metric = json.loads(read(run / "metrics.json"))
            verdict = json.loads(read(run / "verdict.json"))
            assert metric["status"] == "completed" and metric["postprocess"]["status"] == "completed"
            assert metric["postprocess"]["verdict_sha256"] == sha(run / "verdict.json")
            assert verdict["report_sha256"] == sha(run / "report.md")
            strict = bool(verdict.get("found") and isinstance(verdict.get("data"), dict) and not verdict.get("errors"))
            payload = None
            graph = verdict["verification"]["argument_graph"]
            if not strict:
                payload = probe.probe_payload(ledger, str(run))
                assert payload["partial_document"] is True and payload["native_report"]["verified"] is True
                graph = payload["argument_graph"]
                save(out / f"{case['id']}-rep{rep}-partial.json", payload)
            nodes = graph.get("node_declarations", graph["nodes"])
            edges = graph.get("edge_declarations", graph["edges"])
            references = []
            for node in graph["nodes"]:
                for key in ("evidence", "counterevidence"):
                    references.extend(row for row in node.get(key, []) if isinstance(row, dict))
            for edge in edges:
                references.extend(row for row in edge.get("evidence", []) if isinstance(row, dict))
            rows.append({"case": case["id"], "rep": rep, "strict_schema_pass": strict,
                "report_sha256": sha(run / "report.md"), "verdict_sha256": sha(run / "verdict.json"),
                "schema_errors": verdict.get("errors", []), "partial_preview": payload is not None,
                "graph_origin": "frozen_saved_verification" if strict else "frozen_production_partial",
                "node_binding_statuses": dict(Counter(n.get("binding", {}).get("status", "absent") for n in nodes)),
                "edge_binding_statuses": dict(Counter(e.get("binding", {}).get("status", "absent") for e in edges)),
                "reference_statuses": dict(Counter(r.get("status", "absent") for r in references)),
                "diagnostic_code_counts": dict(Counter(d.get("code", "absent") for d in graph.get("diagnostics", []) if isinstance(d, dict))),
                "edge_bindings": [{k: e.get(k) for k in ("id", "from", "to", "relation", "binding")} for e in edges],
                "semantic_checked": False})
            print(case["id"], rep, "strict" if strict else "partial", flush=True)
    assert before == protected(base, cases), "Run artifacts drifted"
    assert before_pool == inventory(pool), "Source pool drifted"
    assert before_code == inventory(package), "Frozen package drifted"
    assert all(Path(module.__file__).resolve().is_relative_to(code)
               for name, module in sys.modules.items() if name.startswith("migloop") and getattr(module, "__file__", None))
    save(out / (ids[0] + "-worker.json"), {"runs": rows, "protected_before": before,
         "protected_stable": True, "source_files": len(before_pool), "source_stable": True,
         "code_stable": True, "frozen_modules_only": True, "model_calls": 0})


def audit(base, out):
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(read(base / "manifest.json"))
    groups = {}
    for case in manifest["cases"]:
        groups.setdefault(case["pool"], []).append(case["id"])
    rows = []
    for ids in groups.values():
        command = [sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()),
                   "--baseline", str(base), "--out", str(out), "--worker", *ids]
        result = subprocess.run(command, capture_output=True, encoding="utf-8")
        save(out / (ids[0] + "-process.json"), {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError("Audit worker failed; original artifacts and failure retained: " + ids[0])
        rows.extend(json.loads(read(out / (ids[0] + "-worker.json")))["runs"])
    totals = {"runs": len(rows), "strict_schema_pass": sum(r["strict_schema_pass"] for r in rows),
              "native_authenticated_partial": sum(r["partial_preview"] for r in rows)}
    for key in ("node_binding_statuses", "edge_binding_statuses", "reference_statuses", "diagnostic_code_counts"):
        counter = Counter()
        for row in rows:
            counter.update(row[key])
        totals[key] = dict(counter)
    save(out / "formal-output-audit.json", {"schema": "migloop-tools10-graph-audit/1",
         "manifest_sha256": sha(base / "manifest.json"), "script_sha256": sha(__file__),
         "totals": totals, "runs": rows, "model_calls": 0, "semantic_checked": False,
         "limitations": ["Reference occurrences are not unique truths.", "Partial projection does not repair the original document.",
                         "Production payload only; no browser rendering assertion.", "Binding is not causal truth."]})
    print(json.dumps(totals))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worker", nargs="+")
    args = parser.parse_args()
    if args.worker:
        worker(args.baseline.resolve(), args.out.resolve(), args.worker)
    else:
        audit(args.baseline.resolve(), args.out.resolve())
