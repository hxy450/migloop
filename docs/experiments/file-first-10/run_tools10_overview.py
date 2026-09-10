"""Manifest-bound overview smoke adapter for the unchanged paired tools runner.

Only ``run`` can call a model. Queue order, prompts, settings, launch, parser,
retries and postprocessing remain owned by run_tools10.py. The two temporary
in-memory hooks below are authenticated by this adapter's frozen file hash.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path


ADAPTER_SCHEMA = "migloop-tools10-overview-adapter/1"
ADAPTER_PATH = Path(__file__).resolve()
_LOADED_ADAPTER_SHA = hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest()
_spec = importlib.util.spec_from_file_location("tools10_overview_unchanged_base", ADAPTER_PATH.with_name("run_tools10.py"))
BASE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BASE)
_BASE_VERIFY = BASE.verify


def _adapter():
    current = BASE.sha(ADAPTER_PATH)
    if current != _LOADED_ADAPTER_SHA:
        raise ValueError("Overview adapter changed after module load")
    return {"schema": ADAPTER_SCHEMA, "path": str(ADAPTER_PATH), "sha256": current}


def verify(out):
    """Read-only: reject adapter drift before invoking the base inventory guard."""
    out = Path(out).resolve()
    expected = _adapter()
    manifest = BASE.read(out / "manifest.json")
    if manifest.get("adapter") != expected:
        raise ValueError("Overview adapter manifest binding missing or changed")
    checked = _BASE_VERIFY(out)
    if checked.get("adapter") != expected or _adapter() != expected:
        raise ValueError("Overview adapter changed during verification")
    return checked


def prepare(out, baseline, *, python=BASE.DEFAULT_PYTHON, source=BASE.REPO, dev_smoke=False):
    """Finalize the adapter binding only inside this new snapshot's preparation."""
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Overview prepare requires a new output directory")
    adapter = _adapter()
    result = BASE.prepare(out, baseline, python=python, source=source, dev_smoke=dev_smoke)
    if _adapter() != adapter:
        raise ValueError("Overview adapter changed during preparation")
    path = out / "manifest.json"
    manifest = BASE.read(path)
    if "adapter" in manifest:
        raise ValueError("Base preparation unexpectedly supplied an adapter")
    manifest["adapter"] = adapter
    # Base.prepare created this file in this call. No existing snapshot is
    # accepted; verify/smoke/run never rewrite this manifest or its artifacts.
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify(out)
    return {**result, "adapter": adapter, "manifest_sha256": BASE.sha(path)}


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _batch_smoke_check(text, request, registry, *, require_overview=False):
    """Verify actual response bytes, exact scope/ledger and registered sources.

    Compatibility accepts the previous raw view without reinterpreting it.
    The live smoke hook additionally requires the new default overview response
    to the base runner's unchanged file request (which has no view selector).
    Count-only overview navigation is valid; it is not file-effect proof.
    """
    body, separator, tail = text.rpartition("\nMIGLOOP_INVESTIGATION_RECEIPT ")
    if not separator:
        return False
    try:
        data, receipt = json.loads(body), json.loads(tail)
        item, = data["items"]
        selected = item["data"]
        if selected["schema"] == "migloop-time-atom/1":
            count = selected["raw_index"]["source_count"]
            schema_ok = (selected.get("view") == "overview"
                         and all(selected["node"].get(k) == registry["scope"].get(k) for k in ("kind", "key", "at")))
        else:
            count = selected.get("source_count")
            schema_ok = selected["schema"] == "migloop-time-view/1" and not require_overview
        if require_overview:
            original, = request["requests"]
            if original["tool"] != "file" or "view" in original["args"]:
                return False
        return (schema_ok and data["schema"] == "migloop-investigation-batch/1"
                and item["status"] == "ok" and item["tool"] == "file"
                and item["scope"] == selected["scope"] == registry["scope"]
                and type(count) is int and count == registry["expected_count"]
                and receipt["schema"] == "migloop-investigation-receipt/1"
                and receipt["ledger"] == data["ledger"] == registry["ledger"]
                and receipt["body_sha256"] == _digest(body)
                and receipt["request_sha256"] == _digest({k: v for k, v in request.items() if k != "sid"}))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def _overview_smoke_check(text, request, registry):
    return _batch_smoke_check(text, request, registry, require_overview=True)


@contextmanager
def _bound_hooks(out):
    """One CLI operation owns its imported base module; restore on every exit."""
    verify(out)
    before = BASE.verify, BASE._batch_smoke_check
    BASE.verify, BASE._batch_smoke_check = verify, _overview_smoke_check
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
