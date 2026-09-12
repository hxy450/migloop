"""One new raw-high run per frozen i20 task; never mutate the old baseline."""

import argparse
import json
import runpy
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ITER = runpy.run_path(str(HERE / "iterate.py"))
BASE = ITER["BASE"]
RAW = BASE.RAW
MATCH = ITER["ROOT"] / "i20-high"
OUT = ITER["BASELINE"].parent / "raw-high-i20-match-20260912"
MARKER = "\n本轮操作面与交付补充："


def prepare_raw_high(out=OUT, match=MATCH):
    matched = ITER["verify"](match)
    if out.exists() or any(out.resolve().is_relative_to(Path(p).resolve()) for p in matched["pools"]):
        raise ValueError("New experiment directory outside source pools required")
    configs, tasks, cases = [], {}, []
    for original in matched["cases"]:
        directory = match / original["id"]
        case_manifest = BASE.read(directory / "manifest.json")
        if case_manifest["model"] != "gpt-5.6-luna" or case_manifest["effort"] != "high":
            raise ValueError("Matched investigator must already be Luna high")
        config = {**BASE.read(directory / "settings.json"), "mcp_servers": {}}
        prompt = (directory / "prompt.md").read_text(encoding="utf-8")
        if prompt.count(MARKER) != 1:
            raise ValueError("Expected exactly one frozen tool-only supplement")
        task = prompt.split(MARKER)[0]
        expected = (
            ITER["PRIOR"] / "raw-prompt.md"
            if original["id"] == "F10-01"
            else ITER["BASELINE"] / original["prompt"]
        ).read_text(encoding="utf-8")
        if task != expected or config["model_reasoning_effort"] != "high":
            raise ValueError("Task or effort mismatch")
        configs.append(config)
        tasks[original["id"]] = task
        cases.append({**original, "prompt": f"tasks/{original['id']}.md"})
    if any(c != configs[0] for c in configs):
        raise ValueError("Other investigator settings differ across cases")
    out.mkdir(parents=True)
    (out / "tasks").mkdir()
    (out / "private").mkdir()
    for case in cases:
        with (out / case["prompt"]).open("x", encoding="utf-8", newline="") as stream:
            stream.write(tasks[case["id"]])
    BASE.save(out / "runtime-settings.json", configs[0])
    for name in ("scoring-core.json", "reference-units.json"):
        shutil.copy2(ITER["BASELINE"] / "private" / name, out / "private" / name)
    cli = RAW.command(cases[0]["pool"], configs[0])[0]
    BASE.save(out / "manifest.json", {
        "schema": "inquiry-matched-raw-high/1", "created": BASE.now(),
        "cases": cases, "model": "gpt-5.6-luna", "effort": "high",
        "repetitions": 1, "concurrency": 2, "timeout_seconds": 1800,
        "automatic_retry": False, "format_repair": False,
        "matched_tool_root": str(match), "matched_manifest_sha256": BASE.sha(match / "manifest.json"),
        "driver_sha256": BASE.sha(Path(__file__)),
        "cli": cli, "cli_sha256": BASE.sha(cli),
        "artifacts": {str(p.relative_to(out)): BASE.sha(p) for p in out.rglob("*") if p.is_file()},
        "comparison": "Same file tasks (including Member), source pools, model/effort and host settings except no MCP. Tool GUIDE/structured workflow remains an arm difference. Historical, not contemporaneously randomized comparison."
    })
    return {"prepared": str(out), "cases": len(cases), "model_calls": 0}


def verify_raw_high(out=OUT):
    manifest = BASE.read(out / "manifest.json")
    match = Path(manifest["matched_tool_root"])
    ITER["verify"](match)
    if BASE.sha(match / "manifest.json") != manifest["matched_manifest_sha256"]:
        raise ValueError("Matched manifest drift")
    if BASE.sha(Path(__file__)) != manifest["driver_sha256"]:
        raise ValueError("Raw high driver drift")
    if BASE.sha(manifest["cli"]) != manifest["cli_sha256"]:
        raise ValueError("CLI binary drift during this cohort")
    for path, expected in manifest["artifacts"].items():
        if BASE.sha(out / path) != expected:
            raise ValueError("Frozen raw high artifact drift: " + path)
    config = BASE.read(out / "runtime-settings.json")
    if config["model_reasoning_effort"] != "high" or config["mcp_servers"]:
        raise ValueError("Raw high requires high and no MCP")
    return manifest


def run_raw_high(case_id, out=OUT):
    manifest = verify_raw_high(out)
    case = next(c for c in manifest["cases"] if c["id"] == case_id)
    RAW.EFFORT = "high"  # This process only; no user/global configuration change.
    metric = RAW.launch(case["pool"], out / "runs" / case_id / "rep1",
                        (out / case["prompt"]).read_text(encoding="utf-8"),
                        BASE.read(out / "runtime-settings.json"), manifest["timeout_seconds"])
    verify_raw_high(out)
    identity_ok = (metric.get("actual_models") == [manifest["model"]]
                   and metric.get("actual_effort") == "high"
                   and metric.get("recording_complete")
                   and metric.get("host_skill_catalog_absent"))
    if not identity_ok:
        raise RuntimeError("Recorded identity/instruction failure; preserve run and stop new scheduling")
    return metric


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify", "run"))
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.mode == "prepare":
        value = prepare_raw_high()
    elif args.mode == "verify":
        verify_raw_high()
        value = {"verified": True, "model_calls": 0}
    else:
        if not args.case:
            parser.error("run requires --case")
        value = run_raw_high(args.case)
    print(json.dumps(value, ensure_ascii=False), flush=True)
