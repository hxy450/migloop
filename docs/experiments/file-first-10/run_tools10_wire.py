"""Manifest-bound wire smoke adapter; historical runners remain byte-unchanged.

Only run starts investigators. Model, task prefix, queue, failure rules, parser
and postprocessing are the unchanged base runner. New wire is checked with the
exact pure decoder copied into that run's frozen source package.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path


ADAPTER_SCHEMA = "migloop-tools10-wire-adapter/1"
ADAPTER_PATH = Path(__file__).resolve()
_LOADED_ADAPTER_SHA = hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest()
_spec = importlib.util.spec_from_file_location("tools10_wire_overview_parent", ADAPTER_PATH.with_name("run_tools10_overview.py"))
OVERVIEW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OVERVIEW)
BASE = OVERVIEW.BASE
_BASE_VERIFY = OVERVIEW._BASE_VERIFY
WIRE_MARKER = "\nMIGLOOP_BATCH_WIRE_RECEIPT "


def _adapter():
    current = BASE.sha(ADAPTER_PATH)
    if current != _LOADED_ADAPTER_SHA:
        raise ValueError("Wire adapter changed after module load")
    return {"schema": ADAPTER_SCHEMA, "path": str(ADAPTER_PATH), "sha256": current,
            "overview_helper": OVERVIEW._adapter()}


def verify(out):
    out = Path(out).resolve()
    expected = _adapter()
    if BASE.read(out / "manifest.json").get("adapter") != expected:
        raise ValueError("Wire adapter manifest binding missing or changed")
    checked = _BASE_VERIFY(out)
    if checked.get("adapter") != expected or _adapter() != expected:
        raise ValueError("Wire adapter changed during verification")
    if not (out / "code/src/migloop/batch_wire.py").is_file():
        raise ValueError("Frozen pure wire decoder is missing")
    return checked


def prepare(out, baseline, *, python=BASE.DEFAULT_PYTHON, source=BASE.REPO, dev_smoke=False):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Wire prepare requires a new output directory")
    adapter = _adapter()
    result = OVERVIEW.prepare(out, baseline, python=python, source=source, dev_smoke=dev_smoke)
    if _adapter() != adapter:
        raise ValueError("Wire adapter changed during preparation")
    path = out / "manifest.json"
    manifest = BASE.read(path)
    if manifest.get("adapter") != adapter["overview_helper"]:
        raise ValueError("Unexpected parent adapter during new snapshot preparation")
    manifest["adapter"] = adapter
    # This manifest was created by this prepare call. Existing experiments are
    # rejected above; verify/smoke/run never rebind or overwrite them.
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify(out)
    return {**result, "adapter": adapter, "manifest_sha256": BASE.sha(path)}


def _decoder(out):
    verify(out)
    path = Path(out).resolve() / "code/src/migloop/batch_wire.py"
    spec = importlib.util.spec_from_file_location("tools10_frozen_pure_wire", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verify(out)
    return module


def _batch_smoke_check(text, request, registry, decoder):
    if WIRE_MARKER not in text:
        return OVERVIEW._batch_smoke_check(text, request, registry, require_overview=True)
    if len(text) > decoder.DEFAULT_MAX_CHARS + 8192:
        return False
    body, _, tail = text.rpartition(WIRE_MARKER)
    if len(tail) > 8192:
        return False
    try:
        receipt = json.loads(tail, object_pairs_hook=decoder._unique_object, parse_constant=decoder._reject_constant)
        normalized = {key: value for key, value in request.items() if key != "sid"}
        if (type(receipt) is not dict or set(receipt) != {
                "schema", "codec", "ledger", "request_sha256", "body_sha256", "canonical_sha256"}
                or receipt["schema"] != "migloop-batch-wire-receipt/1" or receipt["codec"] != decoder.SCHEMA
                or receipt["body_sha256"] != OVERVIEW._digest(body)
                or receipt["request_sha256"] != OVERVIEW._digest(normalized)):
            return False
        data = decoder.unpack(body, request["requests"])
        item, = data["items"]
        original, = request["requests"]
        selected = item["data"]
        count = selected["raw_index"]["source_count"]
        return (original["tool"] == "file" and "view" not in original["args"]
                and data["schema"] == "migloop-investigation-batch/1"
                and receipt["canonical_sha256"] == OVERVIEW._digest(data)
                and receipt["ledger"] == data["ledger"] == registry["ledger"]
                and item["status"] == "ok" and item["tool"] == "file"
                and selected["schema"] == "migloop-time-atom/1" and selected["view"] == "overview"
                and item["scope"] == selected["scope"] == registry["scope"]
                and all(selected["node"].get(k) == registry["scope"].get(k) for k in ("kind", "key", "at"))
                and type(count) is int and count == registry["expected_count"])
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return False


@contextmanager
def _bound_hooks(out):
    decoder = _decoder(out)
    before = BASE.verify, BASE._batch_smoke_check
    BASE.verify = verify
    BASE._batch_smoke_check = lambda text, request, registry: _batch_smoke_check(text, request, registry, decoder)
    try:
        yield
    finally:
        BASE.verify, BASE._batch_smoke_check = before
        verify(out)


def smoke(out):
    with _bound_hooks(out):
        return BASE.smoke(out)


def run_queue(out):
    with _bound_hooks(out):
        return BASE.run_queue(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("prepare", "verify", "smoke", "run"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--python", type=Path, default=BASE.DEFAULT_PYTHON)
    ap.add_argument("--source", type=Path, default=BASE.REPO)
    ap.add_argument("--dev-smoke", action="store_true")
    args = ap.parse_args()
    if args.mode == "prepare":
        if args.baseline is None:
            ap.error("prepare requires --baseline")
        result = prepare(args.out, args.baseline, python=args.python, source=args.source, dev_smoke=args.dev_smoke)
    elif args.mode == "verify":
        result = {"verified": bool(verify(args.out)), "model_calls": 0}
    else:
        result = smoke(args.out) if args.mode == "smoke" else run_queue(args.out)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
