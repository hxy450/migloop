"""Public harness contract only: synthetic pools, opaque contracts, no models."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "docs/experiments/generalization-20260910/run_transfer.py"
spec = importlib.util.spec_from_file_location("transfer_test_runner", RUNNER)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def write(path, text="synthetic"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def replace(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FakeRaw:
    def __init__(self, executable):
        self.executable = executable
        self.calls = []

    def host_skills(self):
        return []

    def settings(self, _):
        return {"model_reasoning_effort": "medium", "features.shell_tool": True, "mcp_servers": {}}

    def command(self, pool, config):
        return [str(self.executable), "exec", "--json", "--ignore-user-config", "-C", str(pool)]

    def launch(self, pool, run, prompt, config, timeout):
        assert timeout == 1800
        assert not run.exists()
        self.calls.append((str(run), prompt, config))
        run.mkdir(parents=True)
        metric = {"status": "completed", "actual_models": ["gpt-5.6-luna"], "actual_effort": "medium",
                  "recording_complete": True, "host_skill_catalog_absent": True, "elapsed_seconds": 0.001,
                  "total_tokens": 123}
        r.save(run / "metrics.json", metric)
        write(run / "report.md", "Synthetic output; not an answer")
        return metric


class FakeBase:
    POSTPROCESS = "synthetic verifier"

    def __init__(self, raw):
        self.RAW = raw

    def prompt(self, raw, sid):
        return raw + "\nTOOLS " + sid

    def settings(self, raw, code, python, pool):
        return {**raw, "features.shell_tool": False, "mcp_servers": {"migloop": {"command": python,
                "args": [str(code)], "env": {"MIGLOOP_FROZEN_POOL": pool["pool"]}}}}

    def postprocess(self, out, manifest, case, run):
        assert case["generation_end"] != case["repair_qualification_start"]
        r.save(run / "verdict.json", {"schema": "migloop-transfer-final-verification/1", "semantic_checked": False})
        return {"status": "completed", "model_calls": 0}


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    source = tmp_path / "source"
    cohorts = []
    # Deliberately neither ten tasks nor any historical pool count.
    for idx, tasks in enumerate((1, 2)):
        cid = f"cohort{idx}"
        pool = source / cid / "pool"
        root = write(pool / f"root{idx}.jsonl", '{"timestamp":"2026-01-01T00:00:00Z"}\n')
        write(pool / "nested/workflow/child.jsonl", "{}\n")
        write(pool / "nested/workflow/child.meta.json", "{}")
        cohorts.append({"id": cid, "pool": f"{cid}/pool", "root_transcript": root.name,
            "sid": str(root.resolve()), "roots": [str(root.resolve())], "files": r.inventory(pool),
            "file_count": 3, "jsonl_count": 2, "generation_end": "2026-01-01T00:01:00Z",
            "repair_qualification_start": "2026-01-01T00:02:00Z", "observation_end": "2026-01-01T00:03:00Z",
            "exposure": {"label": "bounded_synthetic"},
            "tasks": [{"id": f"C{idx}-{n}", "relative_target": f"entry/P{n}.ets", "original_target": f"/p/entry/P{n}.ets"} for n in range(tasks)]})
    source_manifest = source / "source-manifest.json"
    r.save(source_manifest, {"schema": "migloop-transfer-source-freeze/1", "status": "sources_frozen", "cohorts": cohorts})
    candidate = tmp_path / "candidate"
    write(candidate / "code/src/migloop/__init__.py", "# immutable fake runtime\n")
    rows = r.inventory(candidate / "code/src/migloop")
    code = {"algorithm": "sha256", "entries": rows, "content_digest": digest(rows)}
    r.save(candidate / "code-manifest.json", code)
    executable = write(tmp_path / "synthetic-executable", "not executable; never launched")
    r.save(candidate / "manifest.json", {"status": "frozen_ready_for_tools", **r.FIXED,
        "frozen_at": "2026-09-01T00:00:00Z", "code_digest": digest(rows), "python": str(executable)})
    registry = tmp_path / "registry.json"
    r.save(registry, {"schema": "migloop-transfer-registry-validation/1", "source_manifest_sha256": r.sha(source_manifest),
        "code_digest": digest(rows), "runtime_stable": True, "runtime_before": code, "runtime_after": code, "passed": True,
        "cohorts": [{"id": c["id"], "passed": True, "registered_count": 3, "missing": [], "unexpected": [],
                     "registered": [f["path"] for f in c["files"]]} for c in cohorts]})
    contracts = tmp_path / "private/contracts-manifest.json"
    contract_cohorts = []
    for c in cohorts:
        artifacts = []
        for role in ("reference", "core"):
            p = write(contracts.parent / (c["id"] + role + ".opaque"), "not JSON; must never parse private content")
            artifacts.append({"role": role, **r.entry(p)})
        contract_cohorts.append({"id": c["id"], "task_ids": [t["id"] for t in c["tasks"]],
                                 "boundary_gap_reviewed": True, "artifacts": artifacts})
    r.save(contracts, {"schema": "migloop-transfer-contract-freeze/1", "status": "frozen",
        "frozen_at": "2026-09-02T00:00:00Z", "source_manifest_sha256": r.sha(source_manifest),
        "candidate_manifest_sha256": r.sha(candidate / "manifest.json"), "cohorts": contract_cohorts})
    paths = []
    for name in ("file-first-10/run_tools10_wire.py", "file-first-10/run_tools10_overview.py",
                 "file-first-10/run_tools10.py", "file-first-10/run_raw10.py", "2026-09-09-fidelity-cost/run_pair.py"):
        content = "# immutable fake helper"
        if name.endswith("run_pair.py"):
            # Actual public parser/inventory helper, not a simplified stand-in.
            content = (RUNNER.parents[1] / name).read_text(encoding="utf-8")
        p = write(tmp_path / "origins" / name, content)
        paths.append((p, name, r.sha(p)))
    candidate_data = r.read(candidate / "manifest.json")
    candidate_data.update(python_sha256=r.sha(executable), runner_sha256=paths[2][2], raw_runner_sha256=paths[3][2],
        parser_sha256=paths[4][2], adapter={"path": str(paths[0][0]), "sha256": paths[0][2],
        "overview_helper": {"path": str(paths[1][0]), "sha256": paths[1][2]}})
    replace(candidate / "manifest.json", candidate_data)
    contract_data = r.read(contracts)
    contract_data["candidate_manifest_sha256"] = r.sha(candidate / "manifest.json")
    replace(contracts, contract_data)
    raw = FakeRaw(executable)
    base = FakeBase(raw)
    monkeypatch.setattr(r, "helper_sources", lambda _: paths)
    monkeypatch.setattr(r, "helpers", lambda _: (SimpleNamespace(), base, raw))
    return SimpleNamespace(source=source_manifest, candidate=candidate, registry=registry, contracts=contracts,
        out=tmp_path / "prepared", raw=raw, base=base, paths=paths,
        prepare=lambda: r.prepare(tmp_path / "prepared", source_manifest, candidate, r.sha(candidate / "manifest.json"), registry, contracts))


def allow_smoke(bundle):
    manifest = r.verify(bundle.out)
    r.save(bundle.out / "smoke-offline.json", {"passed": True, "model_calls": 0,
        "manifest_sha256": r.sha(bundle.out / "manifest.json"),
        "cohorts": [{"id": c, "passed": True, "batch_content_verified": True, "registry": {"matches": True}} for c in manifest["cohorts"]]})


def test_generic_freeze_opaque_private_contracts_and_equal_questions(bundle):
    assert bundle.prepare()["cases"] == 3
    manifest = r.verify(bundle.out)
    assert manifest["schema"] == "migloop-transfer-run/1"
    assert [c["id"] for c in manifest["cases"]] == ["C0-0", "C1-0", "C1-1"]
    assert not bundle.raw.calls
    for case in manifest["cases"]:
        raw = (bundle.out / case["prompts"]["raw"]).read_text(encoding="utf-8")
        tools = (bundle.out / case["prompts"]["tools"]).read_text(encoding="utf-8")
        assert tools.startswith(raw)
        for field in ("generation_end", "repair_qualification_start", "observation_end"):
            assert case[field] in raw
        assert "资格起点不是调查截断点" in raw
        assert "not JSON" not in raw
    assert not list((bundle.out / "code").rglob("*.pyc"))
    with pytest.raises(FileExistsError):
        bundle.prepare()


@pytest.mark.parametrize("field,value", [("passed", False), ("code_digest", "bad"), ("source_manifest_sha256", "bad")])
def test_registry_gate_refuses_missing_or_wrong_candidate(bundle, field, value):
    data = r.read(bundle.registry)
    data[field] = value
    replace(bundle.registry, data)
    with pytest.raises(ValueError, match="registry"):
        bundle.prepare()
    assert not bundle.out.exists() and not bundle.raw.calls


def test_registry_count_not_enough_missing_source_blocks(bundle):
    data = r.read(bundle.registry)
    data["cohorts"][0]["missing"] = ["nested/workflow/child.jsonl"]
    replace(bundle.registry, data)
    with pytest.raises(ValueError, match="Incomplete"):
        bundle.prepare()


def test_jsonl_only_registry_does_not_certify_sidecars(bundle):
    data = r.read(bundle.registry)
    for cohort in data["cohorts"]:
        cohort["registered"] = [p for p in cohort["registered"] if p.endswith(".jsonl")]
        cohort["registered_count"] = len(cohort["registered"])
    replace(bundle.registry, data)
    with pytest.raises(ValueError, match="Incomplete"):
        bundle.prepare()


@pytest.mark.parametrize("mode", ["unfrozen", "early", "reordered", "gap", "missing_core"])
def test_contract_freeze_precedes_all_model_permission(bundle, mode):
    data = r.read(bundle.contracts)
    if mode == "unfrozen":
        data["status"] = "draft"
    elif mode == "early":
        data["frozen_at"] = "2026-08-01T00:00:00Z"
    elif mode == "reordered":
        data["cohorts"][1]["task_ids"].reverse()
    elif mode == "gap":
        data["cohorts"][0]["boundary_gap_reviewed"] = False
    else:
        data["cohorts"][0]["artifacts"] = data["cohorts"][0]["artifacts"][:1]
    replace(bundle.contracts, data)
    with pytest.raises(ValueError):
        bundle.prepare()
    assert not bundle.raw.calls


@pytest.mark.parametrize("kind", ["pool_added", "pool_changed", "code", "helper", "settings", "prompt", "private", "manifest", "helper_added"])
def test_every_frozen_surface_is_verified(bundle, kind):
    bundle.prepare()
    m = r.read(bundle.out / "manifest.json")
    if kind == "pool_added":
        write(Path(m["cases"][0]["pool"]) / "extra.txt")
    elif kind == "pool_changed":
        write(Path(m["cases"][0]["sid"]), "changed")
    elif kind == "private":
        write(Path(m["private_artifacts"][0]["path"]), "changed")
    elif kind == "helper_added":
        write(bundle.out / "helpers/extra.py")
    else:
        names = {"code": "code/src/migloop/__init__.py", "helper": "helpers/file-first-10/run_raw10.py",
                 "settings": "settings/raw.json", "prompt": "tasks/raw/C0-0.md", "manifest": "manifest.json"}
        write(bundle.out / names[kind], "changed")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        r.verify(bundle.out)


@pytest.mark.parametrize("value", ["../x", "/x", "C:/x", "a/../x", "a\\x", "a//x", ""])
def test_manifest_paths_cannot_escape(value):
    with pytest.raises(ValueError):
        r.relative(value)


def test_anchor_order_is_not_silently_collapsed(bundle):
    source = r.read(bundle.source)
    source["cohorts"][0]["generation_end"] = "2026-01-01T00:02:01Z"
    replace(bundle.source, source)
    with pytest.raises(ValueError, match="order"):
        r.source_cases(bundle.source)


def test_duplicate_task_and_boolean_count_rejected(bundle):
    source = r.read(bundle.source)
    source["cohorts"][0]["jsonl_count"] = True
    replace(bundle.source, source)
    with pytest.raises(ValueError, match="counts"):
        r.source_cases(bundle.source)
    source["cohorts"][0]["jsonl_count"] = 2
    source["cohorts"][1]["tasks"][0]["id"] = "C0-0"
    replace(bundle.source, source)
    with pytest.raises(ValueError, match="duplicate"):
        r.source_cases(bundle.source)


def test_queue_two_reps_no_retry_separate_arms_and_real_guard_artifacts(bundle):
    bundle.prepare()
    allow_smoke(bundle)
    assert r.run_queue(bundle.out, "raw")["status"] == "finished"
    assert len(bundle.raw.calls) == 6
    for case in r.verify(bundle.out)["cases"]:
        for rep in (1, 2):
            run = bundle.out / "raw/runs" / case["id"] / f"rep{rep}"
            assert [a["phase"] for a in r.read(run / "immutability.json")] == ["before", "after"]
            assert r.read(run / "raw-launch-metrics.json")["total_tokens"] == 123
    with pytest.raises(FileExistsError):
        r.run_queue(bundle.out, "raw")
    assert r.run_queue(bundle.out, "tools")["status"] == "finished"
    assert len(bundle.raw.calls) == 12


def test_no_model_without_offline_smoke_or_with_active_queue(bundle):
    bundle.prepare()
    with pytest.raises(FileNotFoundError):
        r.run_queue(bundle.out, "raw")
    allow_smoke(bundle)
    r.save(bundle.out / "ACTIVE.json", {"arm": "tools"})
    with pytest.raises(FileExistsError):
        r.run_queue(bundle.out, "raw")
    assert not bundle.raw.calls


def test_after_run_drift_preserves_failure_and_stops_queue(bundle, monkeypatch):
    bundle.prepare()
    allow_smoke(bundle)
    original = bundle.raw.launch

    def drift(*args):
        metric = original(*args)
        write(bundle.out / "code/src/migloop/__init__.py", "drifted during model call")
        return metric

    monkeypatch.setattr(bundle.raw, "launch", drift)
    result = r.run_queue(bundle.out, "raw")
    assert result["status"] == "stopped"
    assert 1 <= len(bundle.raw.calls) <= 2
    for path, _, _ in bundle.raw.calls:
        run = Path(path)
        assert r.read(run / "metrics.json")["status"] == "harness_error"
        assert r.read(run / "raw-launch-metrics.json")["status"] == "completed"
        assert r.read(run / "immutability.json")[-1]["passed"] is False
    journal = [json.loads(line) for line in (bundle.out / "raw/queue.jsonl").read_text().splitlines()]
    assert journal[-1]["unstarted"] >= 4
    assert len({path for path, _, _ in bundle.raw.calls}) == len(bundle.raw.calls)


def test_frozen_helpers_are_reused_not_old_ten_file_verifier(tmp_path):
    root = RUNNER.parents[1]
    helper_root = tmp_path / "helpers"
    for name in ("run_tools10_wire.py", "run_tools10_overview.py", "run_tools10.py", "run_raw10.py"):
        write(helper_root / "file-first-10" / name, (root / "file-first-10" / name).read_text(encoding="utf-8"))
    write(helper_root / "2026-09-09-fidelity-cost/run_pair.py",
          (root / "2026-09-09-fidelity-cost/run_pair.py").read_text(encoding="utf-8"))
    _, base, raw = r.helpers(tmp_path)
    assert raw.MODEL == "gpt-5.6-luna" and raw.EFFORT == "medium"
    assert base.POSTPROCESS.count("migloop-transfer-final-verification/1") == 1
    assert '(("at", "observation_end"), ("since_ts", "generation_end"))' in base.POSTPROCESS
    base.save(tmp_path / "fallback-verdict.json", {"schema": "migloop-tools10-final-verification/1", "data": None})
    assert r.read(tmp_path / "fallback-verdict.json")["schema"] == "migloop-transfer-final-verification/1"
    raw.parser()
    assert not list(helper_root.rglob("*.pyc"))


def test_registry_cannot_certify_unrelated_paths_by_equal_count(bundle):
    data = r.read(bundle.registry)
    data["cohorts"][0]["registered"][1] = "not-registered.jsonl"
    replace(bundle.registry, data)
    with pytest.raises(ValueError, match="paths differ"):
        bundle.prepare()


def test_real_frozen_candidate_package_contract_read_only():
    # Optional local artifact, never a source pool/ledger/model call.
    candidate = RUNNER.parents[4] / "_migloop-eval-20260909/file-first-10/tools-v4"
    if not candidate.exists():
        pytest.skip("Frozen local tools-v4 package not present")
    manifest, code = r.candidate_check(candidate, "213d7b657a91602db7c777f963eca47c4dcc044340e3fcf6667f7f555f1586c0")
    assert code["content_digest"] == "28b0ab3f71102060a64b9532d7808294096caecbcbf09c5d923e61bd38e5fcbb"
    assert manifest["code_digest"] == code["content_digest"]
    assert code["entries"][0]["path"] == "__init__.py"


def test_real_template_helpers_freeze_into_new_tiny_candidate(tmp_path):
    template = RUNNER.parents[4] / "_migloop-eval-20260909/file-first-10/tools-v4"
    if not template.exists():
        pytest.skip("Frozen local tools-v4 package not present")
    source = tmp_path / "runtime-source"
    write(source / "src/migloop/__init__.py", "# synthetic runtime; no ledger or model\n")
    out = tmp_path / "candidate"
    result = r.freeze_candidate(out, source, template, "213d7b657a91602db7c777f963eca47c4dcc044340e3fcf6667f7f555f1586c0")
    candidate, _ = r.candidate_check(out, result["manifest_sha256"])
    assert candidate["transfer_runner"]["sha256"] == r.sha(RUNNER)
    assert Path(candidate["adapter"]["path"]).is_relative_to(out)
    _, base, raw = r.helpers(out)
    assert base.POSTPROCESS.count("migloop-transfer-final-verification/1") == 1
    assert raw.MODEL == "gpt-5.6-luna"
    assert result["model_calls"] == 0


def test_freeze_candidate_without_gold_or_ten_file_baseline(bundle, monkeypatch):
    out = bundle.out.parent / "new-candidate"
    original_read = r.read

    def public_only(path):
        assert not r.inside(path, bundle.contracts.parent)
        return original_read(path)

    monkeypatch.setattr(r, "read", public_only)
    result = r.freeze_candidate(out, bundle.candidate / "code", bundle.candidate, r.sha(bundle.candidate / "manifest.json"))
    assert result["model_calls"] == 0
    manifest, code = r.candidate_check(out, result["manifest_sha256"])
    assert manifest["schema"] == "migloop-transfer-candidate/1"
    assert "cases" not in manifest and "raw_base" not in manifest
    assert code["entries"][0]["path"] == "__init__.py"
    assert (out / "helpers/file-first-10/run_raw10.py").read_bytes() == bundle.paths[3][0].read_bytes()
    assert not bundle.raw.calls
    with pytest.raises(FileExistsError):
        r.freeze_candidate(out, bundle.candidate / "code", bundle.candidate, r.sha(bundle.candidate / "manifest.json"))


@pytest.mark.parametrize("include_sidecar", [False, True])
def test_registry_smoke_wraps_original_worker_with_all_files(bundle, monkeypatch, include_sidecar):
    bundle.prepare()
    manifest = r.verify(bundle.out)
    cohort = r.read(bundle.source)["cohorts"][0]
    case = {**manifest["cases"][0], "settings": manifest["cases"][0]["configs"]["tools"]}
    paths = [str((Path(case["pool"]) / item["path"]).resolve()) for item in cohort["files"]
             if include_sidecar or item["path"].endswith(".jsonl")]
    bundle.base.REGISTRY_SMOKE = "frozen worker text"
    bundle.base._child_env = lambda _: {"SAFE_TEST": "1"}
    calls = []

    def subprocess_stub(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stderr=b"", stdout=json.dumps({"source_paths": paths, "source_count": len(paths)}).encode())

    monkeypatch.setattr(r.subprocess, "run", subprocess_stub)
    result = r.registry_smoke(bundle.out, manifest, case, cohort, bundle.base)
    assert result["matches"] is include_sidecar
    assert result["expected_count"] == 3 and result["expected_jsonl_count"] == 2
    assert result["registered_jsonl_count"] == 2
    assert len(calls) == 1 and "frozen worker text" in calls[0][0]
    assert calls[0][1]["cwd"] == case["pool"]
