"""Freeze reviewed references, shared file-only tasks and input bytes. Offline."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def validate_contract(selection, reference, core):
    if len(selection["cases"]) != 10 or len({(c["pool"], c["file"]) for c in selection["cases"]}) != 10:
        raise ValueError("Need ten distinct repaired files")
    ids = {c["id"] for c in selection["cases"]}
    if ids != {c["id"] for c in reference["cases"]} or len(ids) != 10:
        raise ValueError("Reference case mismatch")
    unit_ids = [c["id"] + "/" + u["id"] for c in reference["cases"] for u in c["units"]]
    if len(unit_ids) != len(set(unit_ids)) or set(unit_ids) != set(core["units"]):
        raise ValueError("Causal core contract must match reference units exactly")
    if core.get("status") != "approved_for_freeze_before_investigator_runs":
        raise ValueError("Core grading contract not approved")
    return unit_ids


def validate_smoke(smoke):
    summary = read(smoke / "smoke.json")
    m = summary["metrics"]
    if not summary["passed"] or m["actual_models"] != ["gpt-5.6-luna"] or m["actual_effort"] != "medium":
        raise ValueError("Model environment not verified")
    if not m["recording_complete"] or not m["host_skill_catalog_absent"]:
        raise ValueError("Instruction/recording preflight failed")
    if sha(smoke/"runtime-settings.json") != summary["settings_sha256"]:
        raise ValueError("Smoke settings drifted")
    calls = read(smoke/"run/result.json")["calls"]["seq"]
    if not (len(calls) == 1 and calls[0].get("tool") == "command_execution"
            and calls[0].get("status") == "returned" and calls[0].get("exit_code") == 0
            and "get-childitem -force -literalpath ." in str(calls[0].get("input", "")).lower()):
        raise ValueError("Smoke final claim not backed by actual successful command")


def verify_witnesses(selection):
    spec = importlib.util.spec_from_file_location("freeze_originals", HERE/"audit_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pools = {k: module.Pool(v["path"]) for k, v in selection["pools"].items()}
    verified = []
    witnesses = json.loads(re.findall(r"```json\s*\n(.*?)\n```", (HERE/"candidate-0723.md").read_text(encoding="utf-8"), re.S)[0])
    for w in witnesses:
        paths = list(pools["0723"].path.rglob(w["source"]))
        if len(paths) != 1:
            raise ValueError("Ambiguous original basename")
        relative = paths[0].relative_to(pools["0723"].path).as_posix()
        proof = pools["0723"].witness({**w, "source": relative, "contains": [w["contains"]]})
        if proof["timestamp"] != w["timestamp"]:
            raise ValueError("Witness time drift")
        verified.append(proof)
    for w in read(HERE/"candidate-codex.json")["evidence"]:
        row, signature = pools["codex"].record({"source": w["source_basename"],
            "line": w["physical_line"], "sha256": w["record_sha256"]})
        if row.get("timestamp") != w["timestamp_utc"]:
            raise ValueError("Codex witness time drift")
        raw_text = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        fields = "\n".join(module.text_values(row))
        for fragment in w["quote_fragments"]:
            if fragment not in fields and fragment not in raw_text:
                raise ValueError("Codex witness literal drift: " + w["id"])
        verified.append({"pool": "codex", **w, "verified": "bytes_fields_not_causal_truth"})
    for key, p in selection["pools"].items():
        for anchor, expected in [(p["generation_anchor"], p["generation_end"]), (p["end_anchor"], p["observation_end"])]:
            source, line = anchor.rsplit(":", 1)
            row, signature = pools[key].record({"source": source, "line": int(line)})
            if row.get("timestamp") != expected:
                raise ValueError("Original time anchor mismatch")
            verified.append({"pool": key, "source": source, "line": int(line), "sha256": signature, "timestamp": expected})
    return verified


def prepare(out, smoke):
    out, smoke = Path(out).resolve(), Path(smoke).resolve()
    selection, reference, core = (read(HERE/name) for name in ("selection.json", "reference-units.json", "scoring-core.json"))
    units = validate_contract(selection, reference, core)
    validate_smoke(smoke)
    if out.exists() or any(out.is_relative_to(Path(x["path"]).resolve()) for x in selection["pools"].values()):
        raise ValueError("Output must be new and outside input pools")
    proofs = verify_witnesses(selection)
    source_files = []
    for key, pool in selection["pools"].items():
        paths = sorted(Path(pool["path"]).rglob("*.jsonl"))
        if len(paths) != pool["source_files"]:
            raise ValueError("Original corpus file count drift")
        source_files.extend({"pool": key, "path": str(p.resolve()), "sha256": sha(p)} for p in paths)
    out.mkdir(parents=True)
    (out/"private").mkdir()
    private_names = ["reference-units.json", "scoring-core.json", "reference-overview.md", "selection.json",
                     "candidate-0723.md", "candidate-dice.md", "candidate-codex.md", "candidate-codex.json",
                     "review-final-0723.md", "review-final-dice.md", "review-final-rubric.md", "review-log.md", "README.md"]
    for name in private_names:
        shutil.copy2(HERE/name, out/"private"/name)
    for name in ("member-center.md", "splash.md", "dice-index.md"):
        shutil.copy2(HERE.parent/"file-first-luna/review-v2"/name, out/"private"/name)
    write(out/"private/witness-verification.json", proofs)
    shutil.copy2(smoke/"runtime-settings.json", out/"runtime-settings.json")
    task = (HERE/"task-template.md").read_text(encoding="utf-8")
    (out/"tasks").mkdir()
    cases = []
    for case in selection["cases"]:
        pool = selection["pools"][case["pool"]]
        prompt = task.format(target_file=case["file"], pool=pool["path"], **{k:pool[k] for k in (
            "generation_end", "generation_anchor", "observation_end", "end_anchor")})
        prompt += ("\n本轮使用只读 shell（例如 rg 或自己编写的 JSON 解析命令）查看原始 JSONL。"
                   "用中文输出，不要求 YAML 或工具专用坐标。优先在80轮内完成；这是预算提醒而非自动截断。\n")
        name = "tasks/" + case["id"] + ".md"
        (out/name).write_text(prompt, encoding="utf-8")
        cases.append({"id": case["id"], "file": case["file"], "pool": pool["path"], "prompt": name,
                      "exposure": case["exposure"]})
    artifacts = [{"path": p.relative_to(out).as_posix(), "sha256": sha(p)} for p in sorted(out.rglob("*")) if p.is_file()]
    manifest = {"schema": "migloop-file-first-raw10-baseline/1", "status": "frozen_ready_for_raw",
                "frozen_at": datetime.now(timezone.utc).isoformat(), "model": "gpt-5.6-luna", "effort": "medium",
                "cases": cases, "unit_count": len(units), "repetitions": 2, "concurrency": 2,
                "timeout_seconds": 1800, "smoke": str(smoke), "runtime_settings_sha256": sha(out/"runtime-settings.json"),
                "runner_sha256": sha(HERE/"run_raw10.py"), "parser_sha256": sha(HERE.parent/"2026-09-09-fidelity-cost/run_pair.py"),
                "prepare_sha256": sha(Path(__file__)), "source_files": source_files, "artifacts": artifacts,
                "reference_assurance": "Bounded source-backed developer reference with recorded cross-review; not independent human gold or opaque-effect completeness proof"}
    write(out/"manifest.json", manifest)
    print(json.dumps({"out": str(out), "cases": len(cases), "units": len(units), "sources": len(source_files),
                      "manifest_sha256": sha(out/"manifest.json"), "status": manifest["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--smoke", type=Path, required=True)
    args = ap.parse_args()
    prepare(args.out, args.smoke)
