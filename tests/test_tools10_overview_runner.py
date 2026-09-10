"""Overview adapter authenticity and neutral smoke; no actual model launches."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from tests.test_tools10_runner import paired, run as fixture_base


HERE = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-10"
SPEC = importlib.util.spec_from_file_location("tools10_overview_tests", HERE / "run_tools10_overview.py")
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)
ORIGINAL_HASHES = {str(p): run.BASE.sha(p) for p in (HERE / "run_tools10.py", HERE / "run_raw10.py", run.BASE.RAW.OLD_RUNNER)}


@pytest.fixture
def arm(paired, monkeypatch, tmp_path):
    # Reuse the base runner's complete synthetic 436-file pool fixture. Its raw
    # baseline verification stub is the only omitted production freeze layer.
    monkeypatch.setattr(run.BASE.RAW, "verify_manifest", fixture_base.RAW.verify_manifest)
    adapter = tmp_path / "adapter.py"
    adapter.write_bytes(run.ADAPTER_PATH.read_bytes())
    monkeypatch.setattr(run, "ADAPTER_PATH", adapter)
    monkeypatch.setattr(run, "_LOADED_ADAPTER_SHA", run.BASE.sha(adapter))
    monkeypatch.setattr(run.BASE.RAW, "launch", lambda *_a, **_kw: pytest.fail("No model launch in adapter tests"))
    return {**paired, "adapter": adapter}


def prepare(arm):
    return run.prepare(arm["out"], arm["base"], source=arm["source"], python=arm["python"])


def test_prepare_binds_wrapper_bytes_and_returns_final_manifest_hash(arm):
    result = prepare(arm)
    manifest = run.verify(arm["out"])
    assert manifest["adapter"] == {"schema": run.ADAPTER_SCHEMA, "path": str(arm["adapter"]),
                                   "sha256": run.BASE.sha(arm["adapter"])}
    assert result["manifest_sha256"] == run.BASE.sha(arm["out"] / "manifest.json")
    assert result["model_started"] is False
    assert manifest["runner_sha256"] == run.BASE.sha(HERE / "run_tools10.py")
    assert manifest["raw_runner_sha256"] == run.BASE.sha(HERE / "run_raw10.py")
    assert run._BASE_VERIFY(arm["out"]) == manifest  # The base checker is unchanged.
    assert (manifest["model"], manifest["effort"], manifest["repetitions"], manifest["concurrency"],
            manifest["timeout_seconds"]) == ("gpt-5.6-luna", "medium", 2, 2, 1800)
    before = (arm["out"] / "manifest.json").read_bytes()
    run.verify(arm["out"])
    assert (arm["out"] / "manifest.json").read_bytes() == before
    assert {path: run.BASE.sha(path) for path in ORIGINAL_HASHES} == ORIGINAL_HASHES


def test_existing_snapshot_is_never_rebound(arm):
    prepare(arm)
    before = (arm["out"] / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError, match="new output"):
        prepare(arm)
    assert (arm["out"] / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("mutation", ["bytes", "path", "hash", "schema", "missing"])
def test_adapter_drift_rejected_before_model_or_smoke(arm, monkeypatch, mutation):
    prepare(arm)
    path = arm["out"] / "manifest.json"
    manifest = run.BASE.read(path)
    if mutation == "bytes":
        arm["adapter"].write_bytes(arm["adapter"].read_bytes() + b"\n# changed\n")
    elif mutation == "missing":
        del manifest["adapter"]
    else:
        manifest["adapter"][{"hash": "sha256"}.get(mutation, mutation)] = "changed"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(run.BASE, "run_queue", lambda *_: pytest.fail("Model queue must not start"))
    monkeypatch.setattr(run.BASE, "smoke", lambda *_: pytest.fail("Smoke must not start"))
    with pytest.raises(ValueError, match="adapter"):
        run.run_queue(arm["out"])
    with pytest.raises(ValueError, match="adapter"):
        run.smoke(arm["out"])


def test_run_reuses_base_queue_checks_after_and_restores_hooks(arm, monkeypatch):
    prepare(arm)
    original_verify, original_check = run.BASE.verify, run.BASE._batch_smoke_check
    manifest_path = arm["out"] / "manifest.json"
    original_manifest = manifest_path.read_bytes()
    called = []
    def queue(out):
        called.append(out)
        assert run.BASE.verify is run.verify and run.BASE._batch_smoke_check is run._overview_smoke_check
        assert run.BASE.verify(out)["repetitions"] == 2
        return {"status": "finished"}
    monkeypatch.setattr(run.BASE, "run_queue", queue)
    assert run.run_queue(arm["out"])["status"] == "finished" and len(called) == 1
    assert (run.BASE.verify, run.BASE._batch_smoke_check) == (original_verify, original_check)
    assert manifest_path.read_bytes() == original_manifest
    def drift(out):
        arm["adapter"].write_bytes(arm["adapter"].read_bytes() + b"\n# drift during run\n")
    monkeypatch.setattr(run.BASE, "run_queue", drift)
    with pytest.raises(ValueError, match="changed after module load"):
        run.run_queue(arm["out"])
    assert (run.BASE.verify, run.BASE._batch_smoke_check) == (original_verify, original_check)


def sample(schema="migloop-time-atom/1"):
    scope = {"kind": "file", "key": "/project/A.ets", "at": "2026-01-01T00:00:00.000000Z",
             "since_ts": None, "id": "scope:test"}
    registry = {"scope": scope, "ledger": "ledger:test", "expected_count": 146}
    request = {"sid": "s", "requests": [{"tool": "file", "args": {"path": "A.ets", "at": scope["at"], "limit": 1}}],
               "max_chars": 12000}
    selected = {"schema": schema, "scope": scope}
    if schema == "migloop-time-atom/1":
        selected.update(view="overview", node={k: scope[k] for k in ("kind", "key", "at")},
                        raw_index={"source_count": 146}, sections={})
    else:
        selected.update(source_count=146)
    data = {"schema": "migloop-investigation-batch/1", "ledger": registry["ledger"], "items": [
        {"tool": "file", "status": "ok", "scope": scope, "data": selected}]}
    return deepcopy(data), deepcopy(request), deepcopy(registry)


def encoded(data, request, registry, **override):
    body = json.dumps(data, ensure_ascii=False)
    receipt = {"schema": "migloop-investigation-receipt/1", "ledger": registry["ledger"],
               "body_sha256": run._digest(body),
               "request_sha256": run._digest({k: v for k, v in request.items() if k != "sid"}), **override}
    return body + "\nMIGLOOP_INVESTIGATION_RECEIPT " + json.dumps(receipt)


@pytest.mark.parametrize("schema", ["migloop-time-atom/1", "migloop-time-view/1"])
def test_new_overview_and_old_raw_compatibility_are_explicit(schema):
    data, request, registry = sample(schema)
    text = encoded(data, request, registry)
    assert run._batch_smoke_check(text, request, registry)
    assert run._overview_smoke_check(text, request, registry) is (schema == "migloop-time-atom/1")


@pytest.mark.parametrize("mutation", ["error", "deferred", "scope", "body_scope", "node", "count", "ledger", "view", "item_count"])
def test_smoke_rejects_error_deferred_wrong_scope_count_and_ledger(mutation):
    data, request, registry = sample()
    item = data["items"][0]
    if mutation in ("error", "deferred"):
        item["status"] = mutation
    elif mutation == "scope":
        item["scope"] = {**item["scope"], "since_ts": "2026-01-01T00:00:00Z"}
    elif mutation == "body_scope":
        item["data"]["scope"] = {**item["scope"], "key": "/other/A.ets"}
    elif mutation == "node":
        item["data"]["node"]["at"] = "latest"
    elif mutation == "count":
        item["data"]["raw_index"]["source_count"] = 145
    elif mutation == "ledger":
        data["ledger"] = "different"
    elif mutation == "view":
        item["data"]["view"] = "writes"
    else:
        data["items"].append(deepcopy(item))
    assert not run._batch_smoke_check(encoded(data, request, registry), request, registry)


@pytest.mark.parametrize("field", ["body_sha256", "request_sha256"])
def test_smoke_hash_mismatch_and_missing_receipt_rejected(field):
    data, request, registry = sample()
    assert not run._batch_smoke_check(encoded(data, request, registry, **{field: "bad"}), request, registry)
    assert not run._batch_smoke_check(json.dumps(data), request, registry)


def test_actual_smoke_request_cannot_force_overview_selector():
    data, request, registry = sample()
    request["requests"][0]["args"]["view"] = "overview"
    assert not run._overview_smoke_check(encoded(data, request, registry), request, registry)
