"""Freeze private raw-record references and public file-first tasks before runs.

Reuses immutable raw pools, not old directed prompts or model conclusions.
No paid model calls. Refuses overwrite and verifies all referenced record hashes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def module(path):
    spec = importlib.util.spec_from_file_location("file_first_pair_runner", path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = obj
    spec.loader.exec_module(obj)
    return obj


def original(pool, relative, line):
    path = (pool / relative).resolve()
    if not path.is_relative_to(pool.resolve()) or line < 1:
        raise ValueError("Invalid original record location")
    with path.open("rb") as handle:
        for number, raw in enumerate(handle, 1):
            if number == line:
                return raw.rstrip(b"\r\n"), json.loads(raw)
    raise ValueError(f"Missing record {relative}:{line}")


def witness(pool, relative, line):
    raw, row = original(pool, relative, line)
    return {"file": relative, "line": line, "record_sha256": hashlib.sha256(raw).hexdigest(),
            "timestamp": row.get("timestamp"), "uuid": row.get("uuid"),
            "role": (row.get("message") or {}).get("role")}


def verify_legacy(pool, entry):
    raw, row = original(pool, entry["file"], entry["line"])
    if entry["record_sha256"] != hashlib.sha256(raw).hexdigest():
        raise ValueError(f"Legacy witness drift: {entry['id']}")
    value = row
    for key in entry.get("selector") or []:
        value = value[key]
    for marker in entry.get("contains") or []:
        if marker not in json.dumps(row, ensure_ascii=False):
            raise ValueError(f"Legacy marker drift: {entry['id']}")
    for excerpt in entry.get("excerpts", []):
        if not isinstance(value, str) or value[excerpt["start_char"]:][:len(excerpt["text"])] != excerpt["text"]:
            raise ValueError(f"Legacy excerpt drift: {entry['id']}")


def verify_oracle(pool, entry):
    raw, value = original(pool, entry["raw_jsonl"], entry["line_1based"])
    if hashlib.sha256(raw).hexdigest() != entry["record_sha256"]:
        raise ValueError(f"Oracle record drift: {entry['id']}")
    for part in entry["json_pointer"].strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    if not isinstance(value, str) or entry["quote"] not in value:
        raise ValueError(f"Oracle quote drift: {entry['id']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--draft-inventories", type=Path, required=True)
    ap.add_argument("--legacy-witnesses", type=Path, required=True)
    ap.add_argument("--oracle", type=Path, required=True)
    args = ap.parse_args()
    if args.store.exists():
        raise FileExistsError("Baseline directory already exists")
    spec = read(HERE / "reference-spec.json")
    legacy = read(HERE.parent / "2026-09-09-attribution10/legacy-reference.json")
    witnesses = read(args.legacy_witnesses)
    oracle = read(args.oracle)
    pair = module(HERE.parent / "2026-09-09-fidelity-cost/run_pair.py")
    source = args.source.resolve()
    source_manifest = pair.inventory(source / "src/migloop")
    prepared = []
    private = {"schema": "migloop-file-first-reference/1", "version": spec["version"],
               "frozen_at": datetime.now(timezone.utc).isoformat(), "visibility": spec["visibility"],
               "spec_sha256": digest(HERE / "reference-spec.json"), "scoring": spec["scoring"],
               "completeness": spec["completeness"], "cases": []}
    for case in spec["cases"]:
        old = read(args.base / case["parent"] / "case.json")
        pool = Path(old["pool"])
        manifest = pair.inventory(pool)
        if manifest["content_digest"] != old["pool_digest"]:
            raise ValueError(f"Frozen pool drift: {case['id']}")
        inv_path = args.draft_inventories / case["inventory"]
        inv = read(inv_path)
        if Path(inv["pool"]).resolve() != pool.resolve() or inv["target"] != case["target_file"]:
            raise ValueError("Wrong raw inventory")
        for entry in inv["source_files"]:
            if digest(pool / entry["file"]) != entry["sha256"]:
                raise ValueError("Raw inventory source drift")
        anchor_alias, anchor_line = case["generation_anchor"]
        anchor = witness(pool, spec["aliases"][anchor_alias], anchor_line)
        last = None
        for entry in inv["source_files"]:
            with (pool / entry["file"]).open("rb") as handle:
                for n, raw in enumerate(handle, 1):
                    row = json.loads(raw)
                    ts = row.get("timestamp")
                    if isinstance(ts, str) and (last is None or ts > last["timestamp"]):
                        last = {"file": entry["file"], "line": n, "timestamp": ts,
                                "record_sha256": hashlib.sha256(raw.rstrip(b"\r\n")).hexdigest()}
        refs = {}
        events = {}
        for issue in case["issues"]:
            for alias, line in issue["refs"]:
                refs[f"{alias}:{line}"] = witness(pool, spec["aliases"][alias], line)
            for alias, line in issue["changes"]:
                key = (spec["aliases"][alias], line)
                events.setdefault(key, []).append(issue["id"])
        audit = []
        for use in inv["target_calls"] + inv["unresolved_write_capability"]:
            if (use["ts"] or "") <= anchor["timestamp"]:
                continue
            key = (use["file"], use["line"])
            native = use["tool"] in ("Write", "Edit") and str(use["input"].get("file_path", "")).replace("\\", "/").endswith("/" + case["target_file"])
            if key in events:
                if use["pairing"] != "unique" or use["results"][0]["is_error"]:
                    raise ValueError(f"Registered change has no unique success acknowledgment: {key}")
                audit.append({"file": key[0], "line": key[1], "block": use["block"], "tool_use_id": use["tool_use_id"],
                              "tool": use["tool"], "timestamp": use["ts"], "issues": events.pop(key),
                              "effect_basis": "native_success" if native else "manually_inspected_literal_script_and_paired_output",
                              "result": use["results"][0]})
            elif native:
                raise ValueError(f"Unclassified post-anchor native target change: {key}")
        if events:
            raise ValueError(f"Registered changes absent from independent inventory: {events}")
        old_cases = [c for c in legacy["cases"] if c["id"] in case.get("legacy_cases", [])]
        selected_ids = {ref for c in old_cases for ref in c["evidence_ids"]}
        legacy_refs = [w for w in witnesses["witnesses"] if w["id"] in selected_ids]
        for entry in legacy_refs:
            verify_legacy(pool, entry)
        oracle_cases = [c for c in oracle["cases"] if c["id"] in case.get("oracle_cases", [])]
        oracle_refs = [e for e in oracle["evidence"] if oracle_cases and e["id"].startswith("d1-")]
        for entry in oracle_refs:
            verify_oracle(pool, entry)
        case_private = {**case, "generation_anchor": anchor, "end": last, "references": refs,
                        "registered_change_events": audit, "legacy_detail": old_cases,
                        "legacy_witnesses": legacy_refs, "oracle_detail": oracle_cases, "oracle_witnesses": oracle_refs,
                        "raw_inventory": str(inv_path.resolve()), "raw_inventory_sha256": digest(inv_path),
                        "raw_pool_digest": manifest["content_digest"],
                        "known_change_events": len(audit), "unclassified_native_post_anchor": 0,
                        "opaque_effect_completeness_proven": False,
                        "gap_inventory": "raw_inventory.unresolved_write_capability (broad syntax includes read-only false positives; not a count of missing writes)"}
        private["cases"].append(case_private)
        task = (HERE / "task-template.md").read_text(encoding="utf-8").split("---\n", 1)[1].strip() + "\n"
        params = {"target_file": case["target_file"], "pool": str(pool),
                  "allowed_roots_and_children": "\n" + "\n".join("- " + Path(r).name + " 及其同名子代理目录" for r in old["roots"]),
                  "entry_event_or_root": old["current_root"],
                  "generation_anchor_or_explicit_unknown": f"{anchor['timestamp']}，{anchor['file']}@L{anchor['line']}（阶段记录，不等于完整文件快照）。",
                  "change_interval_and_end_event": f"生成锚点之后，至冻结池最后事件 {last['timestamp']}（{last['file']}@L{last['line']}）；边界内未完成调用保留未知。",
                  "history_scope_and_gaps": "允许读取上述全池在生成锚点以前的记录。转录不等于完整文件系统快照；跨调用并发、未记载效应与缺失输入不可默认为已知。"}
        for key, value in params.items():
            task = task.replace("{{" + key + "}}", value)
        if "{{" in task:
            raise ValueError("Unfilled task placeholder")
        prepared.append((case, old, manifest, task))
    args.store.mkdir(parents=True, exist_ok=False)
    write(args.store / "reference.json", private)
    for case, old, manifest, task in prepared:
        dest = args.store / case["case"]
        dest.mkdir()
        (dest / "common-task.md").write_text(task, encoding="utf-8")
        write(dest / "pool-manifest.json", manifest)
        write(dest / "source-manifest.json", source_manifest)
        doc = {**old, "case": case["case"], "file": case["target_file"], "created_at": private["frozen_at"],
               "source": str(source), "source_code_id": "f882a3a", "source_digest": source_manifest["content_digest"],
               "common_task_sha256": digest(dest / "common-task.md"), "task_revision": "file-first/1",
               "private_reference_sha256": digest(args.store / "reference.json"), "selection_id": case["id"]}
        write(dest / "case.json", doc)
    manifest = {"schema":"migloop-file-first-baseline/1", "created_at":private["frozen_at"],
                "model":"gpt-5.6-luna", "effort":"medium", "tool_transport":"code-host",
                "repetitions_per_arm":2, "case_count":len(prepared),
                "issue_families":sum(len(c["issues"]) for c in spec["cases"]),
                "reference_sha256":digest(args.store / "reference.json"),
                "source_digest":source_manifest["content_digest"],
                "runner_sha256":digest(HERE.parent / "2026-09-09-fidelity-cost/run_pair.py"),
                "preparation_sha256":digest(__file__), "task_template_sha256":digest(HERE / "task-template.md"),
                "status":"prepared_not_run", "development_set_not_holdout":True}
    write(args.store / "baseline.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
