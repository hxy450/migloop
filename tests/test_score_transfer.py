"""Synthetic transfer score contracts only; no model, runtime ledger, or gold."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/experiments/generalization-20260910"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


s = load(DOC / "score_transfer.py", "transfer_score_test")
r = load(DOC / "run_transfer.py", "transfer_score_fixture_runner")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def put(path, value):
    return write(path, json.dumps(value, ensure_ascii=False))


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / "source"
    cohorts = []
    # Arbitrary task and per-file unit counts: not 13, 10, 26, or one unit/file.
    for i, count in enumerate((1, 2)):
        cid = f"group{i}"
        pool = source / cid / "pool"
        root = write(pool / "root.jsonl", '\n'.join(json.dumps(row, ensure_ascii=True) for row in [
            {"timestamp": "2026-01-01T00:00:00Z"},
            {"timestamp": "2026-01-01T00:00:01Z", "message": {"content": [
                {"type": "tool_use", "id": "native-use", "name": "Read", "input": {"file_path": "/p.ets"}}]}},
            {"timestamp": "2026-01-01T00:00:02Z", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "native-use", "content": 'mentions invented-id and quoted "value"; \u771f\u5b9e'}]}},
            {"timestamp": "2026-01-01T00:00:03Z", "type": "response_item", "payload": {
                "type": "function_call", "call_id": "native-codex", "name": "functions.exec_command", "arguments": "{}"}},
            {"timestamp": "2026-01-01T00:00:04Z", "type": "response_item", "payload": {
                "type": "function_call_output", "call_id": "native-codex", "output": "mentions invented-id"}}]) + '\n')
        write(pool / "aux.txt", "untimed original navigation\n")
        cohorts.append({"id": cid, "pool": f"{cid}/pool", "root_transcript": "root.jsonl",
            "sid": str(root.resolve()), "roots": [str(root.resolve())], "files": r.inventory(pool),
            "file_count": 2, "jsonl_count": 1, "generation_end": "2026-01-01T00:01:00Z",
            "repair_qualification_start": "2026-01-01T00:02:00Z", "observation_end": "2026-01-01T00:03:00Z",
            "exposure": {"label": "synthetic"},
            "tasks": [{"id": f"G{i}-{n}", "relative_target": f"entry/P{n}.ets"} for n in range(count)]})
    source_path = put(source / "source-manifest.json", {"schema": "migloop-transfer-source-freeze/1",
                     "status": "sources_frozen", "cohorts": cohorts})
    candidate = tmp_path / "candidate"
    write(candidate / "code/src/migloop/__init__.py", "# synthetic immutable package\n")
    helper_names = ["file-first-10/run_tools10_wire.py", "file-first-10/run_tools10_overview.py",
                    "file-first-10/run_tools10.py", "file-first-10/run_raw10.py", "2026-09-09-fidelity-cost/run_pair.py"]
    helpers = []
    for name in helper_names:
        body = (ROOT / "docs/experiments" / name).read_text(encoding="utf-8") if name.endswith("run_pair.py") else "# never executed"
        helpers.append(write(candidate / "helpers" / name, body))
    parser = load(helpers[-1], "score_fixture_native_inventory")
    code = parser.inventory(candidate / "code/src/migloop")
    put(candidate / "code-manifest.json", code)
    exe = write(tmp_path / "not-an-executable", "hash-only; never launched")
    candidate_manifest = {"schema": "migloop-transfer-candidate/1", "status": "frozen_ready_for_tools", **r.FIXED,
        "frozen_at": "2026-09-01T00:00:00Z", "code_digest": code["content_digest"], "python": str(exe),
        "python_sha256": r.sha(exe), "runner_sha256": r.sha(helpers[2]), "raw_runner_sha256": r.sha(helpers[3]),
        "parser_sha256": r.sha(helpers[4]), "adapter": {"path": str(helpers[0]), "sha256": r.sha(helpers[0]),
        "overview_helper": {"path": str(helpers[1]), "sha256": r.sha(helpers[1])}}}
    put(candidate / "manifest.json", candidate_manifest)
    registry = put(tmp_path / "registry.json", {"schema": "migloop-transfer-registry-validation/1",
        "source_manifest_sha256": r.sha(source_path), "code_digest": code["content_digest"],
        "runtime_stable": True, "runtime_before": code, "runtime_after": code, "passed": True,
        "cohorts": [{"id": c["id"], "passed": True, "registered_count": 2, "missing": [], "unexpected": [],
                     "registered": [f["path"] for f in c["files"]]} for c in cohorts]})
    contracts_path = tmp_path / "private/contracts.json"
    contract_cohorts = []
    for i, c in enumerate(cohorts):
        reference = write(contracts_path.parent / f"{c['id']}-reference.opaque", "NOT JSON: reference contents must not be parsed")
        core = put(contracts_path.parent / f"{c['id']}-core.json", {"schema": "migloop-causal-core-contract/1",
            "units": {f"{t['id']}/unit{k}": {"core_pass": "synthetic criterion"}
                      for n, t in enumerate(c["tasks"]) for k in range(i + n + 1)}})
        contract_cohorts.append({"id": c["id"], "task_ids": [t["id"] for t in c["tasks"]],
            "boundary_gap_reviewed": True, "artifacts": [{"role": role, **r.entry(p, p.name)}
                                                          for role, p in (("reference", reference), ("core", core))]})
    put(contracts_path, {"schema": "migloop-transfer-contract-freeze/1", "status": "frozen",
        "frozen_at": "2026-09-02T00:00:00Z", "source_manifest_sha256": r.sha(source_path),
        "candidate_manifest_sha256": r.sha(candidate / "manifest.json"), "cohorts": contract_cohorts})
    _, cases, _, _, private = r.gates(source_path, candidate, r.sha(candidate / "manifest.json"), registry, contracts_path)
    base = tmp_path / "package"
    shutil.copytree(candidate / "code", base / "code")
    shutil.copytree(candidate / "helpers", base / "helpers")
    shutil.copyfile(DOC / "run_transfer.py", base / "run_transfer.py")
    for case in cases:
        case["prompts"], case["configs"] = {}, {}
        for arm in ("raw", "tools"):
            prompt = f"tasks/{arm}/{case['id']}.md"
            config = f"settings/{arm}/{case['id']}.json"
            write(base / prompt, f"{arm} {case['id']} {case['generation_end']} original public task")
            put(base / config, {})
            case["prompts"][arm], case["configs"][arm] = prompt, config
    manifest = {"schema": r.SCHEMA, "status": "frozen_ready", **r.FIXED,
        "candidate": str(candidate), "inputs": {key: r.entry(path) for key, path in
        (("source_manifest", source_path), ("candidate_manifest", candidate / "manifest.json"),
         ("registry", registry), ("contracts", contracts_path))},
        "private_artifacts": private, "code_digest": code["content_digest"], "code_entries": code["entries"],
        "cases": cases, "cohorts": [c["id"] for c in cohorts], "executables": [r.entry(exe)],
        "helper_origins": [r.entry(p) for p in helpers], "runner_origin": r.entry(DOC / "run_transfer.py"),
        "artifacts": r.inventory(base)}
    put(base / "manifest.json", manifest)
    put(base / "READY.json", {"manifest_sha256": r.sha(base / "manifest.json")})
    context = s.verify_package(base)
    return SimpleNamespace(base=base, grades=tmp_path / "grades", context=context, source=source_path,
                           contracts=contracts_path, candidate=candidate, registry=registry)


def run(bundle, case="G0-0", rep=1, arm="raw", status="completed", report=True):
    context = bundle.context
    task = context["cases"][case]
    directory = bundle.base / arm / "runs" / case / f"rep{rep}"
    write(directory / "prompt.md", (bundle.base / task["prompts"][arm]).read_text(encoding="utf-8"))
    if report:
        write(directory / "report.md", f"{case} {arm} repetition {rep}\nObserved repair; qualified cause. Hypothesis only. A false claim.")
    metric = {"status": status, "condition": arm, "cohort": task["cohort"],
        "transfer_manifest_sha256": context["manifest_sha256"], "code_digest": context["manifest"]["code_digest"],
        "automatic_retry": False, "format_repair": False, "actual_models": ["gpt-5.6-luna"],
        "actual_effort": "medium", "recording_complete": True, "host_skill_catalog_absent": True,
        "elapsed_seconds": 10, "system_elapsed_seconds": 12,
        "usage": {"input_total": 100, "output": 25, "cache_read": 80, "cache_creation": 0}}
    if arm == "tools":
        verdict = {"schema": "migloop-transfer-final-verification/1", "report_sha256": s.sha(directory / "report.md") if report else None,
                   "found": True, "data": {"schema": "migloop-verdict/3"}, "errors": ["synthetic bad edge"],
                   "verification": {"identity": {"bound": False}, "argument_graph": {"nodes": [], "edges": []}}}
        put(directory / "verdict.json", verdict)
        metric["postprocess"] = {"status": "completed", "elapsed_seconds": 1, "verdict_sha256": s.sha(directory / "verdict.json")}
    put(directory / "metrics.json", metric)
    put(directory / "immutability.json", [{"phase": p, "passed": True} for p in ("before", "after")])
    return directory


def grade(bundle, case="G0-0", rep=1, arm="raw"):
    context = bundle.context
    task, directory, core = s._case(context, case, rep, arm)
    return {"schema": s.GRADE_SCHEMA, "case": case, "rep": rep, "condition": arm, "cohort": task["cohort"],
        "transfer_manifest_sha256": context["manifest_sha256"], "metrics_sha256": s.sha(directory / "metrics.json"),
        "report_sha256": s.sha(directory / "report.md"), "core_contract_sha256": core["sha256"],
        "claims_review_complete": True,
        "units": [{"id": uid, "outcome": "correct", "reason": "reviewed local explanation",
                   "report_spans": ["Observed repair; qualified cause."], "evidence": [{"source": "root.jsonl", "line": 1}]}
                  for uid in core["required"][case]],
        "claims": [{"id": "cause", "outcome": "supported", "reason": "original supports local cause",
                    "report_spans": ["Observed repair; qualified cause."], "evidence": [{"source": "root.jsonl", "line": 1}], "major_error": False}]}


def store_grade(bundle, value):
    return put(bundle.grades / value["condition"] / value["case"] / f"rep{value['rep']}.json", value)


def queue(bundle, arm="raw", finished=True):
    jobs = [(c, rep) for c in bundle.context["cases"] for rep in (1, 2)]
    records = [{"event": "start", "condition": arm, "jobs": len(jobs), "time": "2026-09-10T00:00:00Z"}]
    for case, rep in jobs:
        records.extend({"event": e, "case": case, "rep": rep, "time": "2026-09-10T00:00:01Z"} for e in ("launch", "finish"))
    if finished:
        records.append({"event": "end", "status": "finished", "unstarted": 0, "unstarted_jobs": [], "time": "2026-09-10T00:00:30Z"})
    return write(bundle.base / arm / "queue.jsonl", "\n".join(json.dumps(r) for r in records))


def complete(bundle, arm="raw"):
    for case in bundle.context["cases"]:
        for rep in (1, 2):
            run(bundle, case, rep, arm)
            store_grade(bundle, grade(bundle, case, rep, arm))
    queue(bundle, arm)


def test_real_frozen_verifier_and_generic_denominators(bundle):
    complete(bundle)
    data = s.summarize(bundle.base, bundle.grades, condition="raw")
    assert data["aggregate_ready"] and data["runs_expected"] == 6
    assert [c["runs_expected"] for c in data["cohorts"]] == [2, 4]
    assert [c["aggregate"]["units"] for c in data["cohorts"]] == [2, 10]
    assert [c["aggregate"]["distinct_files"] for c in data["cohorts"]] == [1, 2]
    assert data["costs"]["tokens_total"]["sum"] == 750  # cache not added again
    assert data["costs"]["cache_read_tokens"]["sum"] == 480
    assert data["costs"]["investigator_elapsed_seconds"]["sum"] == 60
    assert data["costs"]["system_elapsed_seconds"]["sum"] == 72
    assert data["costs"]["postprocess_elapsed_seconds"]["sum"] is None
    assert data["queue"]["makespan_seconds"] == 30
    assert not list(bundle.base.rglob("*.pyc"))


@pytest.mark.parametrize("change", ["duplicate", "omitted", "foreign", "span", "boolrep", "majorhypothesis", "claimduplicate", "review"])
def test_invalid_grade_structure(bundle, change):
    run(bundle, "G1-0")
    g = grade(bundle, "G1-0")
    if change == "duplicate": g["units"][1] = copy.deepcopy(g["units"][0])
    elif change == "omitted": g["units"].pop()
    elif change == "foreign": g["units"][0]["id"] = "foreign"
    elif change == "span": g["claims"][0]["report_spans"] = ["not in report"]
    elif change == "boolrep": g["rep"] = True
    elif change == "majorhypothesis": g["claims"][0].update(outcome="explicitly_hypothetical", major_error=True)
    elif change == "claimduplicate": g["claims"].append(copy.deepcopy(g["claims"][0]))
    elif change == "review": g.pop("claims_review_complete")
    with pytest.raises(ValueError): s.validate_grade(bundle.base, "G1-0", 1, g, condition="raw")


@pytest.mark.parametrize("field", ["case", "rep", "condition", "cohort", "report_sha256", "metrics_sha256", "core_contract_sha256", "transfer_manifest_sha256"])
def test_artifact_binding_rejects_borrowed_grade(bundle, field):
    run(bundle)
    g = grade(bundle)
    g[field] = 2 if field == "rep" else "borrowed"
    with pytest.raises(ValueError, match="binding"):
        s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")


@pytest.mark.parametrize("surface", ["pool", "core", "reference", "candidate", "helper", "code", "runner", "settings", "registry"])
def test_frozen_surface_drift_refused(bundle, surface):
    paths = {"pool": bundle.source.parent / "group0/pool/aux.txt",
             "core": bundle.context["cores"]["group0"]["path"],
             "reference": bundle.contracts.parent / "group0-reference.opaque",
             "candidate": bundle.candidate / "manifest.json", "helper": bundle.base / "helpers/file-first-10/run_raw10.py",
             "code": bundle.base / "code/src/migloop/__init__.py", "runner": bundle.base / "run_transfer.py",
             "settings": bundle.base / "settings/raw/G0-0.json", "registry": bundle.registry}
    write(paths[surface], paths[surface].read_text(encoding="utf-8") + "\nDRIFT")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        s.verify_package(bundle.base)


def test_partial_not_correct_and_clean_report_not_core_pass(bundle):
    run(bundle)
    g = grade(bundle)
    g["units"][0]["outcome"] = "partial"
    g["claims"] = []
    data = s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")
    assert data["correct"] == 0 and data["partial"] == 1 and not data["file_pass"]
    assert data["attribution_precision"] is None
    assert data["full_report_no_contradicted_or_unsupported_assertions"]
    g["units"][0]["outcome"] = "correct"
    g["claims"] = [{"id": "possible", "outcome": "explicitly_hypothetical", "major_error": False,
                    "reason": "expressly unresolved mechanism", "report_spans": ["Hypothesis only."], "evidence": []}]
    data = s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")
    assert data["asserted_claims"] == 0 and data["attribution_precision"] is None and data["file_pass"]


def test_ordinary_false_claim_vs_major_and_no_schema_penalty(bundle):
    run(bundle, arm="tools")
    g = grade(bundle, arm="tools")
    g["claims"][0].update(outcome="contradicted", report_spans=["A false claim."])
    data = s.validate_grade(bundle.base, "G0-0", 1, g, condition="tools")
    assert data["file_pass"] and not data["full_report_no_contradicted_or_unsupported_assertions"]
    g["claims"][0]["major_error"] = True
    data = s.validate_grade(bundle.base, "G0-0", 1, g, condition="tools")
    assert data["correct"] == 1 and not data["file_pass"] and data["major_errors"] == 1


def test_complete_tools_bad_mechanical_kept_separate(bundle):
    complete(bundle, "tools")
    data = s.summarize(bundle.base, bundle.grades, condition="tools")
    assert data["aggregate_ready"]
    assert all(row["grade"]["file_pass"] for row in data["runs"])
    assert all(row["mechanical"]["document_checks_pass"] is False for row in data["runs"])


def test_pending_not_zero_and_no_cohort_early_aggregate(bundle):
    run(bundle)
    store_grade(bundle, grade(bundle))
    data = s.summarize(bundle.base, bundle.grades, condition="raw")
    assert data["runs_adjudicated"] == 1 and not data["aggregate_ready"]
    assert all(c["aggregate"] is None for c in data["cohorts"])
    assert data["runs"][1]["grade"] is None
    assert data["costs"]["tokens_total"] == {"observed_runs": 1, "expected_runs": 6, "sum": 125, "mean": 125, "complete": False}


@pytest.mark.parametrize("status,expected", [("timeout", "terminal_no_final"), ("incomplete", "terminal_no_final"),
                                             ("completed", "pending_final_delivery_audit"), ("harness_error", "harness_failure")])
def test_terminal_no_final_vs_harness_failure(bundle, status, expected):
    run(bundle, status=status, report=False)
    data = s.summarize(bundle.base, bundle.grades, condition="raw")
    row = data["runs"][0]
    assert row["state"] == expected and row["tokens_total"] == 125
    if expected == "terminal_no_final":
        assert row["grade"]["missing"] == 1 and row["grade"]["wrong"] == 0
        assert row["grade"]["full_report_no_contradicted_or_unsupported_assertions"] is None
    else:
        assert row["grade"] is None


def test_timeout_with_final_requires_manual_grade(bundle):
    run(bundle, status="timeout")
    data = s.summarize(bundle.base, bundle.grades, condition="raw")
    assert data["runs"][0]["state"] == "pending_adjudication" and data["runs"][0]["grade"] is None
    assert s.validate_grade(bundle.base, "G0-0", 1, grade(bundle), condition="raw")["file_pass"]


@pytest.mark.parametrize("failure", ["recording", "postprocess", "prompt", "immutability", "model"])
def test_infrastructure_failures_never_autograde_missing(bundle, failure):
    directory = run(bundle, arm="tools", status="timeout", report=False)
    metric = s.read(directory / "metrics.json")
    if failure == "recording": metric["recording_complete"] = False
    elif failure == "postprocess": metric["postprocess"]["status"] = "error"
    elif failure == "prompt": write(directory / "prompt.md", "different case task")
    elif failure == "immutability": put(directory / "immutability.json", [{"phase": "before", "passed": True}])
    elif failure == "model": metric["actual_models"] = ["other"]
    put(directory / "metrics.json", metric)
    data = s.summarize(bundle.base, bundle.grades, condition="tools")
    assert data["runs"][0]["state"] == "harness_failure" and data["runs"][0]["grade"] is None


def test_completed_grades_without_finished_whole_queue_not_aggregate(bundle):
    complete(bundle)
    queue(bundle, finished=False)
    assert not s.summarize(bundle.base, bundle.grades, condition="raw")["aggregate_ready"]


def test_extra_attempt_not_silently_selected(bundle):
    complete(bundle)
    write(bundle.base / "raw/runs/G0-0/rep3/metrics.json", "{}")
    with pytest.raises(ValueError, match="Unregistered"):
        s.summarize(bundle.base, bundle.grades, condition="raw")


def test_queue_duplicate_attempt_rejected(bundle):
    complete(bundle)
    path = bundle.base / "raw/queue.jsonl"
    rows = path.read_text(encoding="utf-8").splitlines()
    rows.insert(-1, rows[1])
    write(path, "\n".join(rows))
    with pytest.raises(ValueError, match="duplicate queue"):
        s.summarize(bundle.base, bundle.grades, condition="raw")


def test_wrong_arm_metrics_rejected(bundle):
    directory = run(bundle)
    metric = s.read(directory / "metrics.json")
    metric["condition"] = "tools"
    put(directory / "metrics.json", metric)
    with pytest.raises(ValueError, match="binding"):
        s.summarize(bundle.base, bundle.grades, condition="raw")


def test_no_overwrite_and_non_json_values(tmp_path):
    path = tmp_path / "summary.json"
    s.save(path, {"pending": None})
    with pytest.raises(FileExistsError): s.save(path, {"pending": False})
    assert s.read(path) == {"pending": None}
    with pytest.raises(ValueError): s._json('{"units":{},"units":{}}')
    with pytest.raises(ValueError): s._json('{"cost":NaN}')
    assert s._stat([None, False, 0])["observed_runs"] == 1
    assert s._native_ids({"type": "tool_result", "tool_use_id": "real-result",
                          "content": [{"type": "tool_use", "id": "output-example-not-a-call"}]}) == {"real-result"}


@pytest.mark.parametrize("evidence,match", [
    ({"source": "root.jsonl", "line": 999999}, "line does not exist"),
    ({"source": "root.jsonl", "line": 1, "timestamp": "2026-01-02T00:00:00Z"}, "timestamp differs"),
    ({"source": "root.jsonl", "line": 1, "ts": None}, "timestamp differs"),
    ({"source": "aux.txt", "line": 1, "time": "2026-01-01T00:00:00Z"}, "timestamp differs"),
    ({"source": "root.jsonl", "line": 3, "excerpt": "invented excerpt"}, "excerpt absent"),
    ({"source": "root.jsonl", "line": 3, "call_id": "invented-id"}, "native call/result field"),
    ({"source": "root.jsonl", "line": 5, "callid": "invented-id"}, "native call/result field"),
    ({"source": "root.jsonl", "line": 3, "pointer": "/message/content/0/type", "excerpt": "invented-id"}, "excerpt absent"),
    ({"source": "root.jsonl", "line": 3, "pointer": "/missing"}, "pointer does not resolve"),
])
def test_raw_locator_and_literal_field_counterexamples(bundle, evidence, match):
    run(bundle)
    g = grade(bundle)
    g["units"][0]["evidence"] = [evidence]
    with pytest.raises(ValueError, match=match):
        s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")


@pytest.mark.parametrize("line,callid", [(2, "native-use"), (3, "native-use"), (4, "native-codex"), (5, "native-codex")])
def test_native_ids_are_typed_fields_not_success_or_pair_authentication(bundle, line, callid):
    run(bundle)
    g = grade(bundle)
    g["units"][0]["evidence"] = [{"source": "root.jsonl", "line": line, "call_id": callid}]
    data = s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")
    assert data["evidence_checks"]["typed_id_field_match"] == 1
    assert data["source_policy_verified"] is False
    assert "do not certify native registration" in data["evidence_check_scope"]


def test_decoded_excerpt_unknown_aux_and_opaque_reference_not_claimed_verified(bundle):
    run(bundle)
    g = grade(bundle)
    g["units"][0]["evidence"] = [
        {"source": "root.jsonl", "line": 3, "ts": "2026-01-01T01:00:02+01:00",
         "pointer": "/message/content/0/content", "excerpt": "\u771f\u5b9e", "call_id": "native-use"},
        {"source": "aux.txt", "line": 1, "timestamp": None, "excerpt": "untimed original"}, "REF-unit-1"]
    data = s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")
    assert data["evidence_checks"]["opaque_cross_reference_occurrences"] == 1
    assert data["evidence_checks"]["excerpt_occurrences"] == 2
    assert data["evidence_checks"]["literal_timestamp_match"] == 1
    assert data["evidence_checks"]["absent_timestamp_occurrences"] == 1


def test_reused_native_session_across_reps_rejected_without_new_required_field(bundle):
    complete(bundle)
    for rep in (1, 2):
        directory = bundle.base / "raw/runs/G0-0" / f"rep{rep}"
        metric = s.read(directory / "metrics.json")
        metric["session_id"] = "reused-native-session"
        put(directory / "metrics.json", metric)
        g = grade(bundle, rep=rep)
        store_grade(bundle, g)
    with pytest.raises(ValueError, match="Reused.*native run identity"):
        s.summarize(bundle.base, bundle.grades, condition="raw")


def test_optional_native_hash_and_session_audit(bundle):
    directory = run(bundle)
    transcript = write(directory / "transcript.jsonl", json.dumps({"type": "session_meta", "payload": {"id": "session-one"}}))
    metric = s.read(directory / "metrics.json")
    metric.update(session_id="session-other", transcript_sha256=s.sha(transcript))
    put(directory / "metrics.json", metric)
    data = s.summarize(bundle.base, bundle.grades, condition="raw")
    assert data["runs"][0]["state"] == "harness_failure"
    assert "native_session_identity_differs" in data["runs"][0]["harness_failures"]
    metric["session_id"] = "session-one"
    put(directory / "metrics.json", metric)
    write(transcript, transcript.read_text(encoding="utf-8") + "\nchanged")
    data = s.summarize(bundle.base, bundle.grades, condition="raw")
    assert "native_transcript_hash_not_bound" in data["runs"][0]["harness_failures"]


def test_no_final_reports_remain_failures_in_complete_denominator(bundle):
    complete(bundle)
    directory = bundle.base / "raw/runs/G0-0/rep1"
    # Synthesize a terminal no-answer run without deleting any real artifact.
    write(directory / "report.md", "")
    metric = s.read(directory / "metrics.json")
    metric["status"] = "incomplete"
    put(directory / "metrics.json", metric)
    new_grades = bundle.grades.parent / "no-final-grades"
    for old in bundle.grades.rglob("*.json"):
        if old.relative_to(bundle.grades).as_posix() != "raw/G0-0/rep1.json":
            write(new_grades / old.relative_to(bundle.grades), old.read_text(encoding="utf-8"))
    data = s.summarize(bundle.base, new_grades, condition="raw")
    assert data["aggregate_ready"]
    cohort = data["cohorts"][0]["aggregate"]
    assert cohort["missing"] == 1 and cohort["file_macro_correct_attribution_coverage"] == 0.5
    assert cohort["full_reports_claim_reviewed"] == 1
    assert cohort["full_reports_no_contradicted_or_unsupported_assertions"] == 1


def test_report_and_mechanical_drift_not_silently_scored(bundle):
    directory = run(bundle, arm="tools")
    g = grade(bundle, arm="tools")
    write(directory / "report.md", "a replaced report")
    with pytest.raises(ValueError, match="binding"):
        s.validate_grade(bundle.base, "G0-0", 1, g, condition="tools")
    with pytest.raises(ValueError, match="Mechanical report binding"):
        s.summarize(bundle.base, bundle.grades, condition="tools")


def test_foreign_or_opaque_major_not_accepted(bundle):
    run(bundle)
    g = grade(bundle)
    g["claims"][0].update(outcome="contradicted", major_error=True, evidence=["opaque-only"])
    with pytest.raises(ValueError, match="original source basis"):
        s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")
    g["claims"][0]["evidence"] = [{"source": "other-pool.jsonl", "line": 1}]
    with pytest.raises(ValueError, match="foreign or ambiguous"):
        s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")


def test_score_output_does_not_parse_or_emit_reference_content(bundle, capsys):
    out = bundle.base.parent / "new-summary.json"
    s.main(["summarize", "--base", str(bundle.base), "--condition", "raw", "--grades", str(bundle.grades), "--out", str(out)])
    assert "reference contents must not be parsed" not in out.read_text(encoding="utf-8")
    assert "synthetic criterion" not in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        s.main(["summarize", "--base", str(bundle.base), "--condition", "raw", "--grades", str(bundle.grades), "--out", str(out)])


def test_null_call_id_is_explicit_absence_not_verified_native_id(bundle):
    run(bundle)
    g = grade(bundle)
    g["units"][0]["evidence"] = [{"source": "root.jsonl", "line": 1, "call_id": None}]
    result = s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")
    assert result["evidence_checks"]["absent_typed_call_id_occurrences"] == 1
    assert "typed_id_field_match" not in result["evidence_checks"]
    g["units"][0]["evidence"][0]["line"] = 2
    with pytest.raises(ValueError, match="declared absent"):
        s.validate_grade(bundle.base, "G0-0", 1, g, condition="raw")


@pytest.mark.parametrize("suffix", ["txt", "json", "jsonl"])
def test_json_looking_attachments_and_unknown_journal_do_not_authenticate_native_source(tmp_path, suffix):
    path = write(tmp_path / f"data.{suffix}", json.dumps({"timestamp": "2026-01-01T00:00:00Z",
                 "type": "tool_use", "id": "looks-native", "input": {"text": "literal body"}}))
    context = {"source": {"cohorts": [{"id": "c", "pool": ".", "files": [{"path": path.name}]}]},
               "manifest": {"inputs": {"source_manifest": {"path": str(tmp_path / "source-manifest.json")}}}}
    e = {"source": path.name, "line": 1, "excerpt": "literal body", "pointer": "/input/text"}
    result = s._evidence([e], context, "c")
    assert result["excerpt_occurrences"] == 1  # Independent decoded literal only.
    if suffix == "jsonl":
        e.update(ts="2026-01-01T00:00:00Z", call_id="looks-native")
        result = s._evidence([e], context, "c")
        assert result["jsonl_source_policy_unverified_occurrences"] == 1
        assert result["typed_id_field_match"] == 1
        assert result["native_source_verified"] == 0
    else:
        assert result["text_attachment_occurrences"] == 1
        with pytest.raises(ValueError, match="timestamp differs"):
            s._evidence([{**e, "ts": "2026-01-01T00:00:00Z"}], context, "c")
        with pytest.raises(ValueError, match="native call/result field"):
            s._evidence([{**e, "call_id": "looks-native"}], context, "c")
        absent = s._evidence([{**e, "ts": None, "call_id": None}], context, "c")
        assert absent["absent_typed_call_id_occurrences"] == 1
