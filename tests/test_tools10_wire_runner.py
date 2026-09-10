"""Wire smoke checks bind the exact frozen codec and unchanged experiment."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from migloop import batch_wire
from migloop.investigation import _delivery
from tests.test_tools10_runner import paired, run as fixture_base

HERE = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-10"
SPEC = importlib.util.spec_from_file_location("tools10_wire_tests", HERE / "run_tools10_wire.py")
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


@pytest.fixture
def arm(paired, monkeypatch, tmp_path):
    monkeypatch.setattr(run.BASE.RAW, "verify_manifest", fixture_base.RAW.verify_manifest)
    adapter = tmp_path / "wire_adapter.py"
    adapter.write_bytes(run.ADAPTER_PATH.read_bytes())
    monkeypatch.setattr(run, "ADAPTER_PATH", adapter)
    monkeypatch.setattr(run, "_LOADED_ADAPTER_SHA", run.BASE.sha(adapter))
    source = paired["source"] / "src/migloop/batch_wire.py"
    source.write_bytes(Path(batch_wire.__file__).read_bytes())
    monkeypatch.setattr(run.BASE.RAW, "launch", lambda *_a, **_kw: pytest.fail("No model launches in tests"))
    return {**paired, "adapter": adapter}


def prepare(arm):
    return run.prepare(arm["out"], arm["base"], source=arm["source"], python=arm["python"])


def test_new_manifest_binds_both_adapters_and_frozen_decoder(arm):
    prepare(arm)
    manifest = run.verify(arm["out"])
    assert manifest["adapter"] == run._adapter()
    assert run._decoder(arm["out"]).SCHEMA == batch_wire.SCHEMA
    before = (arm["out"] / "manifest.json").read_bytes()
    assert run._BASE_VERIFY(arm["out"]) == manifest
    with pytest.raises(FileExistsError):
        prepare(arm)
    assert (arm["out"] / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("target", ["adapter", "decoder", "binding"])
def test_changed_binding_rejects_before_queue(arm, monkeypatch, target):
    prepare(arm)
    if target == "adapter":
        arm["adapter"].write_bytes(arm["adapter"].read_bytes() + b"\n# drift\n")
    elif target == "decoder":
        path = arm["out"] / "code/src/migloop/batch_wire.py"
        path.write_bytes(path.read_bytes() + b"\n# drift\n")
    else:
        path = arm["out"] / "manifest.json"
        value = run.BASE.read(path)
        value["adapter"]["overview_helper"]["sha256"] = "bad"
        path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(run.BASE, "run_queue", lambda *_: pytest.fail("Must reject before queue"))
    with pytest.raises(ValueError):
        run.run_queue(arm["out"])


def test_hooks_restore_on_error_and_do_not_change_historical_runners(arm, monkeypatch):
    paths = [HERE / "run_tools10.py", HERE / "run_tools10_overview.py", HERE / "run_raw10.py", run.BASE.RAW.OLD_RUNNER]
    hashes = {path: run.BASE.sha(path) for path in paths}
    prepare(arm)
    before = run.BASE.verify, run.BASE._batch_smoke_check
    def fail(_out):
        assert run.BASE.verify is run.verify
        raise RuntimeError("smoke failure")
    monkeypatch.setattr(run.BASE, "smoke", fail)
    with pytest.raises(RuntimeError):
        run.smoke(arm["out"])
    assert (run.BASE.verify, run.BASE._batch_smoke_check) == before
    assert {path: run.BASE.sha(path) for path in paths} == hashes


def packet():
    scope = {"kind": "file", "key": "/project/A.ets", "at": "2026-09-10T00:00:00Z", "since_ts": None, "id": "scope:fixed"}
    request = {"sid": "sid", "requests": [{"tool": "file", "args": {"path": scope["key"], "at": scope["at"], "limit": 1}}], "max_chars": 12000}
    selected = {"schema": "migloop-time-atom/1", "view": "overview", "scope": scope,
                "node": {key: scope[key] for key in ("kind", "key", "at")},
                "raw_index": {"source_count": 3}, "sections": {}}
    data = {"schema": "migloop-investigation-batch/1", "ledger": "ledger:fixed", "items": [
        {"item_index": 0, "tool": "file", "args": request["requests"][0]["args"], "status": "ok",
         "scope": scope, "data": selected, "delivery": _delivery(selected)}]}
    registry = {"scope": scope, "ledger": data["ledger"], "expected_count": 3}
    return data, request, registry


def wire(data, request):
    body = json.dumps(batch_wire.pack(data, request["requests"]), ensure_ascii=False)
    receipt = {"schema": "migloop-batch-wire-receipt/1", "codec": batch_wire.SCHEMA, "ledger": data["ledger"],
               "body_sha256": run.OVERVIEW._digest(body), "canonical_sha256": run.OVERVIEW._digest(data),
               "request_sha256": run.OVERVIEW._digest({key: value for key, value in request.items() if key != "sid"})}
    return body + run.WIRE_MARKER + json.dumps(receipt)


def test_neutral_wire_smoke_checks_actual_original_request_and_response():
    data, request, registry = packet()
    text = wire(data, request)
    assert run._batch_smoke_check(text, request, registry, batch_wire)
    for changed in ({**registry, "expected_count": 4}, {**registry, "ledger": "other"}):
        assert not run._batch_smoke_check(text, request, changed, batch_wire)
    assert not run._batch_smoke_check(text.replace("ledger:fixed", "ledger:forged", 1), request, registry, batch_wire)
    assert not run._batch_smoke_check(text, {**request, "max_chars": 13000}, registry, batch_wire)


@pytest.mark.parametrize("change", ["count_bool", "scope", "view", "explicit_view", "tool", "state"])
def test_self_consistent_wrong_canonical_is_not_a_passing_live_smoke(change):
    data, request, registry = deepcopy(packet())
    selected = data["items"][0]["data"]
    if change == "count_bool":
        selected["raw_index"]["source_count"] = True
        registry["expected_count"] = 1
    elif change == "scope":
        selected["node"]["at"] = "2026-09-11T00:00:00Z"
    elif change == "view":
        selected["view"] = "records"
    elif change == "explicit_view":
        request["requests"][0]["args"]["view"] = "overview"
    elif change == "tool":
        request["requests"][0]["tool"] = data["items"][0]["tool"] = "search"
    else:
        data["items"][0]["status"] = "error"
    assert not run._batch_smoke_check(wire(data, request), request, registry, batch_wire)
