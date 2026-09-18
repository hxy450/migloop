"""Replay archived i14 input/CLI/wire with only the selected backend changed.

No skills, job files, rewritten prompts, parent context, or automatic retries.
The archived interfaces module is loaded unchanged against the selected engine.
"""
import argparse
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("i14_recording", HERE / "run_i14_delivery.py")
RECORD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RECORD)
RAW, BASE = RECORD.RAW, RECORD.BASE


def input_texts(path):
    texts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        item = row.get("payload", {})
        if row.get("type") == "response_item" and item.get("type") == "message" and item.get("role") == "user":
            texts.append("\n".join(x.get("text", "") for x in item.get("content", []) if isinstance(x, dict)))
    return texts


def module_bootstrap(code, wire):
    return (f"import sys,importlib.util;sys.path.insert(0,{str(code)!r});"
            f"s=importlib.util.spec_from_file_location('migloop.inquiry.i14_wire',{str(wire)!r});"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);")


def describe_wire(python, code, wire):
    program = module_bootstrap(code, wire) + (
        "import asyncio,inspect,json,hashlib;"
        "server=m.build_mcp('metadata-only-unused.sqlite');"
        "print(json.dumps({'guide_sha256':hashlib.sha256(m.GUIDE.encode()).hexdigest(),"
        "'tools':[t.model_dump() for t in asyncio.run(server.list_tools())],"
        "'engine':inspect.getfile(m.Engine),'store':inspect.getfile(m.Store),"
        "'check':inspect.getfile(m.check)},ensure_ascii=False))"
    )
    return json.loads(subprocess.check_output([python, "-I", "-B", "-X", "utf8", "-c", program], text=True, encoding="utf-8"))


def prepare(out, historical_case, backend):
    if out.exists():
        raise FileExistsError(out)
    archive = historical_case / "runs/inquiry/rep1"
    old = RAW.read(historical_case / "manifest.json")
    command = RAW.read(archive / "command.json")
    prompt = (archive / "prompt.md").read_text(encoding="utf-8")
    if prompt not in input_texts(archive / "transcript.jsonl"):
        raise ValueError("Archived prompt differs from the actual historical user input")
    out.mkdir(parents=True)
    shutil.copy2(archive / "prompt.md", out / "prompt.md")
    source_code = Path(old["code_root"]) if backend == "historical" else BASE.REPO / "src"
    code = out / "backend/src"
    (code / "migloop").mkdir(parents=True)
    shutil.copy2(source_code / "migloop/__init__.py", code / "migloop/__init__.py")
    shutil.copytree(source_code / "migloop/inquiry", code / "migloop/inquiry",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    wire = out / "transport/interfaces_i14.py"
    wire.parent.mkdir()
    original_wire = Path(old["code_root"]) / "migloop/inquiry/interfaces.py"
    shutil.copy2(original_wire, wire)
    config = copy.deepcopy(command["settings"])
    mcp = config["mcp_servers"]["inquiry"]
    python = mcp["command"]
    db = out / "index.sqlite"
    original_description = describe_wire(python, Path(old["code_root"]), original_wire)
    description = describe_wire(python, code, wire)
    if any(original_description[k] != description[k] for k in ("guide_sha256", "tools")):
        raise ValueError("MCP instructions/schema drifted")
    RAW.save(out / "wire-description.json", description)
    importing = [python, "-I", "-B", "-X", "utf8", "-c",
        f"import sys;sys.path.insert(0,{str(code)!r});from migloop.inquiry.__main__ import main;main()",
        "--db", str(db), "import", "--pool", command["cwd"]]
    imported = subprocess.run(importing, capture_output=True, text=True, encoding="utf-8", check=True, timeout=180)
    RAW.save(out / "import.json", json.loads(imported.stdout))
    mcp["args"][mcp["args"].index("-c") + 1] = module_bootstrap(code, wire) + "m.build_mcp(sys.argv[sys.argv.index('--db')+1]).run()"
    mcp["args"][mcp["args"].index("--db") + 1] = str(db)
    argv = list(command["argv"])
    index = next(i for i, value in enumerate(argv) if value.startswith("mcp_servers="))
    formatter = RAW.parser().toml_value
    if argv[index] != "mcp_servers=" + formatter(command["settings"]["mcp_servers"]):
        raise ValueError("Archived config no longer round-trips to its actual argv")
    argv[index] = "mcp_servers=" + formatter(config["mcp_servers"])
    if len(subprocess.list2cmdline(argv)) > 30000:
        raise ValueError("Command exceeds Windows launch budget")
    cli_version = subprocess.check_output([argv[0], "--version"], text=True).strip()
    if cli_version != "codex-cli 0.154.0":
        raise ValueError("CLI version differs from the historical run")
    RAW.save(out / "settings.json", config)
    RAW.save(out / "expected-command.json", {"argv": argv, "cwd": command["cwd"]})
    alignment = {
        "prompt_file_byte_identical": RAW.sha(out / "prompt.md") == RAW.sha(archive / "prompt.md"),
        "prompt_matches_historical_native_user_input": True,
        "argv_changed_indices": [i for i, (a, b) in enumerate(zip(argv, command["argv"])) if a != b],
        "only_mcp_launch_argument_changed": all(a == b for i, (a, b) in enumerate(zip(argv, command["argv"])) if i != index),
        "non_mcp_settings_identical": {k:v for k,v in config.items() if k != "mcp_servers"} == {k:v for k,v in command["settings"].items() if k != "mcp_servers"},
        "cwd_identical": True, "wire_source_byte_identical": RAW.sha(wire) == RAW.sha(original_wire),
        "wire_guide_and_tool_schema_identical": True, "cli_version": cli_version,
        "changed": ["selected backend source", "isolated index", "MCP bootstrap paths"],
        "uncontrolled": ["new thread/time and stochastic model output", "remote alias snapshot and service load not pinned", "historical Python package lock and CLI binary hash were not archived"]
    }
    RAW.save(out / "alignment.json", alignment)
    sources = [historical_case / "manifest.json", archive / "prompt.md", archive / "command.json", archive / "transcript.jsonl", original_wire]
    dependencies = [Path(__file__), HERE / "run_i14_delivery.py", HERE / "run_card.py",
                    BASE.REPO / "docs/experiments/file-first-10/run_raw10.py", RAW.OLD_RUNNER, Path(argv[0]), *sources]
    RAW.save(out / "manifest.json", {
        "schema": "migloop-i14-exact-input-replay/1", "backend": backend, "case": old["case"],
        "workspace": command["cwd"], "historical_case": str(historical_case), "code_root": str(code), "index_path": str(db),
        "model": old["model"], "effort": old["effort"], "timeout_seconds": old["timeout_seconds"],
        "fresh_thread": True, "fork": False, "automatic_retry": False, "new_skill_or_job": False,
        "frozen": {"backend/src": BASE.inventory(code), "transport": BASE.inventory(wire.parent)},
        "source_pool": {"path": command["cwd"], "inventory": BASE.inventory(Path(command["cwd"]))},
        "files": {name: RAW.sha(out / name) for name in ["prompt.md", "settings.json", "expected-command.json", "wire-description.json", "alignment.json"]},
        "dependencies": {str(p):RAW.sha(p) for p in dependencies},
        "environment": subprocess.check_output([python, "-m", "pip", "freeze"], text=True, encoding="utf-8").splitlines()
    })
    verify(out)
    print(json.dumps({"prepared": str(out), "backend": backend, "alignment": alignment}, ensure_ascii=False), flush=True)


def verify(out):
    manifest = BASE.verify(out)
    pool = manifest["source_pool"]
    if BASE.inventory(Path(pool["path"])) != pool["inventory"]:
        raise ValueError("Original source pool drifted")
    return manifest


def run(out):
    manifest = verify(out)
    expected = RAW.read(out / "expected-command.json")
    config = RAW.read(out / "settings.json")
    def exact_command(cwd, settings):
        if Path(cwd).resolve() != Path(expected["cwd"]).resolve() or settings != config:
            raise ValueError("Launcher changed the archived configuration")
        return list(expected["argv"])
    RAW.command = exact_command
    RAW.MODEL, RAW.EFFORT = manifest["model"], manifest["effort"]
    prompt = (out / "prompt.md").read_text(encoding="utf-8")
    metrics = RAW.launch(Path(expected["cwd"]), out / "run", prompt, config, manifest["timeout_seconds"])
    verify(out)
    RAW.save(out / "post-run-integrity.json", {
        "frozen_inputs_unchanged": True,
        "native_user_prompt_identical": prompt in input_texts(out / "run/transcript.jsonl") if metrics["recording_complete"] else False,
        "actual_argv_identical": RAW.read(out / "run/command.json")["argv"] == expected["argv"]
    })
    print(json.dumps({"metrics": metrics, "submission": RECORD.capture(out)}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "verify"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--historical-case", type=Path)
    parser.add_argument("--backend", choices=("historical", "current"), default="current")
    args = parser.parse_args()
    if args.mode == "prepare":
        if not args.historical_case:
            parser.error("prepare requires --historical-case")
        prepare(args.out.resolve(), args.historical_case.resolve(), args.backend)
    elif args.mode == "run":
        run(args.out.resolve())
    else:
        verify(args.out.resolve())
        print("verified")
