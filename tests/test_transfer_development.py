"""Exercise tools-only candidate iteration against immutable parent evidence."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from tests.test_run_transfer import bundle, r as runner, write, replace, digest, allow_smoke


@pytest.fixture
def development(bundle, tmp_path):
    bundle.prepare()
    candidate = tmp_path / "candidate2"
    shutil.copytree(bundle.candidate, candidate)
    write(candidate / "code/src/migloop/__init__.py", "# changed synthetic runtime\n")
    rows = runner.inventory(candidate / "code/src/migloop")
    code = {"algorithm": "sha256", "entries": rows, "content_digest": digest(rows)}
    replace(candidate / "code-manifest.json", code)
    manifest = runner.read(candidate / "manifest.json")
    manifest.update(code_digest=digest(rows), frozen_at="2026-09-03T00:00:00Z")
    replace(candidate / "manifest.json", manifest)
    registry = tmp_path / "registry2.json"
    reg = runner.read(bundle.registry)
    reg.update(code_digest=digest(rows), runtime_before=code, runtime_after=code)
    replace(registry, reg)
    out = tmp_path / "development"
    return SimpleNamespace(parent=bundle, candidate=candidate, registry=registry, out=out,
        prepare=lambda: runner.prepare_development(out, bundle.out, candidate,
            runner.sha(candidate / "manifest.json"), registry))


def test_new_candidate_reuses_exact_private_bytes_and_public_questions(development):
    d = development
    parent = runner.verify(d.parent.out)
    private_before = {p["path"]: Path(p["path"]).read_bytes() for p in parent["private_artifacts"]}
    parent_before = (d.parent.out / "manifest.json").read_bytes()
    result = d.prepare()
    m = runner.verify(d.out)
    assert result["model_calls"] == 0 and result["cases"] == 3
    assert not d.parent.raw.calls
    assert m["code_digest"] != parent["code_digest"]
    assert m["private_artifacts"] == parent["private_artifacts"]
    for name in ("source_manifest", "contracts"):
        assert m["inputs"][name] == parent["inputs"][name]
    assert (d.parent.out / "manifest.json").read_bytes() == parent_before
    assert all(Path(p).read_bytes() == body for p, body in private_before.items())
    assert m["development_parent"]["exposure"] == "development_exposed"
    assert m["development_parent"]["raw_reused"] is True
    for case, old in zip(m["cases"], parent["cases"]):
        assert set(case["prompts"]) == set(case["configs"]) == {"tools"}
        assert (d.out / case["prompts"]["tools"]).read_bytes() == (d.parent.out / old["prompts"]["tools"]).read_bytes()
    assert not (d.out / "raw").exists()


def test_raw_queue_is_refused_before_lock_or_any_model_call(development):
    d = development
    d.prepare()
    with pytest.raises(ValueError, match="only tools"):
        runner.run_queue(d.out, "raw")
    assert not d.parent.raw.calls
    assert not (d.out / "ACTIVE.json").exists()
    assert not (d.out / "raw").exists()


def test_tools_queue_keeps_all_cases_and_two_repetitions(development):
    d = development
    d.prepare()
    allow_smoke(SimpleNamespace(out=d.out))
    assert runner.run_queue(d.out, "tools")["status"] == "finished"
    assert len(d.parent.raw.calls) == 6  # FakeRaw only: no real model subprocess.
    assert len(list((d.out / "tools/runs").glob("*/rep*/report.md"))) == 6
    assert not (d.out / "raw").exists() and not (d.parent.out / "raw").exists()
    assert not (d.out / "ACTIVE.json").exists()


@pytest.mark.parametrize("kind", ["source", "private", "parent_prompt", "parent_runner", "parent_ready", "candidate_code", "registry"])
def test_input_drift_prevents_preparation_without_output_or_calls(development, kind):
    d = development
    p = runner.read(d.parent.out / "manifest.json")
    paths = {"source": Path(p["cases"][0]["sid"]), "private": Path(p["private_artifacts"][0]["path"]),
        "parent_prompt": d.parent.out / p["cases"][0]["prompts"]["tools"],
        "parent_runner": d.parent.out / "run_transfer.py", "parent_ready": d.parent.out / "READY.json",
        "candidate_code": d.candidate / "code/src/migloop/__init__.py", "registry": d.registry}
    write(paths[kind], "changed")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        d.prepare()
    assert not d.out.exists() and not d.parent.raw.calls


@pytest.mark.parametrize("kind", ["duplicate", "missing_sidecar", "boolean_count", "wrong_cohort", "runtime_mismatch"])
def test_new_registry_must_cover_exact_sources_and_runtime(development, kind):
    d = development
    reg = runner.read(d.registry)
    cohort = reg["cohorts"][0]
    if kind == "duplicate":
        cohort["registered"].append(cohort["registered"][0])
    elif kind == "missing_sidecar":
        cohort["registered"] = [p for p in cohort["registered"] if p.endswith(".jsonl")]
    elif kind == "boolean_count":
        cohort["registered_count"] = True
    elif kind == "wrong_cohort":
        cohort["id"] = "unknown"
    else:
        reg["runtime_after"] = {}
    replace(d.registry, reg)
    with pytest.raises(ValueError, match="registry"):
        d.prepare()
    assert not d.out.exists() and not d.parent.raw.calls


@pytest.mark.parametrize("kind", ["private", "source", "prompt", "parent_runner", "registry", "runtime"])
def test_reused_and_new_artifact_drift_also_fails_after_preparation(development, kind):
    d = development
    d.prepare()
    m = runner.read(d.out / "manifest.json")
    paths = {"private": Path(m["private_artifacts"][0]["path"]), "source": Path(m["cases"][0]["sid"]),
        "prompt": d.out / m["cases"][0]["prompts"]["tools"], "parent_runner": d.parent.out / "run_transfer.py",
        "registry": d.registry, "runtime": d.out / "code/src/migloop/__init__.py"}
    write(paths[kind], "changed")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        runner.verify(d.out)
    assert not d.parent.raw.calls


def test_original_candidate_cannot_be_relabelled_as_new(development):
    d = development
    with pytest.raises(ValueError, match="must be new"):
        runner.prepare_development(d.out, d.parent.out, d.parent.candidate,
            runner.sha(d.parent.candidate / "manifest.json"), d.parent.registry)
    assert not d.out.exists()


@pytest.mark.parametrize("where", ["parent", "candidate", "source"])
def test_output_cannot_overlap_frozen_inputs(development, where):
    d = development
    parent = runner.read(d.parent.out / "manifest.json")
    root = {"parent": d.parent.out, "candidate": d.candidate, "source": Path(parent["cases"][0]["pool"])}[where]
    out = root / "new-output"
    with pytest.raises(ValueError, match="separate|overlap"):
        runner.prepare_development(out, d.parent.out, d.candidate, runner.sha(d.candidate / "manifest.json"), d.registry)
    assert not out.exists()


def test_development_parent_cannot_form_recursive_chain(development):
    d = development
    d.prepare()
    with pytest.raises(ValueError, match="chains"):
        runner.prepare_development(d.out.parent / "iteration2", d.out, d.candidate,
            runner.sha(d.candidate / "manifest.json"), d.registry)
