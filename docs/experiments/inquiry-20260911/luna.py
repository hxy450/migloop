"""One frozen Luna run. No retry, extra investigator, or answer repair."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PRIOR = Path("C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/longchain-20260911-member")
OUT = Path("C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/inquiry-luna-20260911-member")


def load_previous():
    spec = importlib.util.spec_from_file_location("inquiry_previous", HERE.parent / "longchain-20260911/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_command(python):
    return [python, "-I", "-B", "-X", "utf8", "-c",
            f"import sys;sys.path.insert(0,{str(OUT / 'code/src')!r});"
            "from migloop.inquiry.__main__ import main;main()",
            "--db", str(OUT / "index.sqlite")]


async def preflight(config):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=config["command"], args=config["args"])
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            initialized = await session.initialize()
            listing = await session.list_tools()
            names = sorted(tool.name for tool in listing.tools)
            if names != ["investigate", "page", "submit"] or not initialized.instructions:
                raise ValueError("Unexpected MCP contract")
            return {"tools": names, "guide": initialized.instructions, "model_calls": 0,
                    "queries_executed": 0}


def prepare(base, old):
    if OUT.exists():
        raise FileExistsError(OUT)
    OUT.mkdir(parents=True)
    package = OUT / "code/src/migloop"
    package.mkdir(parents=True)
    shutil.copy2(REPO / "src/migloop/__init__.py", package / "__init__.py")
    before = base.tree_manifest(REPO / "src/migloop/inquiry")
    shutil.copytree(REPO / "src/migloop/inquiry", package / "inquiry",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    if base.tree_manifest(package / "inquiry") != before:
        raise ValueError("Source changed during freeze")
    for name in ("luna.py", "luna-protocol.md"):
        shutil.copy2(HERE / name, OUT / name)
    for name in ("reference-units.json", "scoring-core.json"):
        shutil.copy2(PRIOR / name, OUT / name)
    cmd = module_command(old["python"])
    built = subprocess.run(cmd + ["import", "--pool", old["case"]["pool"]],
                           capture_output=True, text=True, encoding="utf-8", check=True, timeout=180)
    base.save(OUT / "import.json", json.loads(built.stdout))
    raw = base.read(PRIOR / "raw-settings.json")
    config = {**raw, "mcp_servers": {"inquiry": {
        "command": cmd[0], "args": cmd[1:] + ["mcp"],
        "required": True, "startup_timeout_sec": 45, "tool_timeout_sec": 120}}}
    if {**config, "mcp_servers": raw["mcp_servers"]} != raw:
        raise ValueError("Non-MCP settings changed")
    base.RAW.command(old["case"]["pool"], config)
    readiness = asyncio.run(preflight(config["mcp_servers"]["inquiry"]))
    base.save(OUT / "preflight.json", readiness)
    base.save(OUT / "settings.json", config)
    prompt = (PRIOR / "raw-prompt.md").read_bytes().decode("utf-8") + (
        "\n本轮操作与交付补充（替换上一段操作面，任务与原始材料不变）：\n"
        "你可自由使用只读shell和inquiry MCP，不需要via；保留原始读取能力，不调用第二个模型。\n"
        "下面是新MCP的完整通用接口说明，不含本题答案。调查结束后由你自己submit完整inquiry/1稿；"
        "可根据核验诊断补查，但不要为连通而编造历史关系。最终只返回最后一次submit的report_id、"
        "source_sha256及简短摘要，不重复长稿，不提交未经submit的新原因。未证断点也可以如实提交。\n\n"
        + readiness["guide"])
    (OUT / "prompt.md").write_bytes(prompt.encode("utf-8"))
    with sqlite3.connect(OUT / "index.sqlite") as db:
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("runs", "frames", "visible")}
    if any(counts.values()):
        raise ValueError("Experiment index contains prior investigation")
    base.save(OUT / "manifest.json", {
        "schema": "inquiry-luna-diagnostic/1", "frozen_at": base.now(),
        "case": old["case"], "pool": old["pool"], "python": old["python"],
        "model": old["model"], "effort": old["effort"], "timeout_seconds": old["timeout_seconds"],
        "code": base.tree_manifest(package), "code_commit": "11c536c",
        "driver_sha256": base.sha(HERE / "luna.py"),
        "prior_manifest_sha256": base.sha(PRIOR / "manifest.json"),
        "artifacts": {p.name: base.sha(p) for p in OUT.iterdir() if p.is_file() and p.suffix != ".sqlite"},
        "initial_query_counts": counts, "automatic_retry": False,
        "format_repair": False, "planned_model_sessions": 1,
        "reference_visibility": "reviewers only; outside allowed source pool"})
    return {"prepared": str(OUT), "model_calls": 0, "import": json.loads(built.stdout)}


def verify(base):
    manifest = base.read(OUT / "manifest.json")
    for name, digest in manifest["artifacts"].items():
        if base.sha(OUT / name) != digest:
            raise ValueError("Frozen artifact drift: " + name)
    if base.sha(HERE / "luna.py") != manifest["driver_sha256"]:
        raise ValueError("Driver drift")
    if base.sha(PRIOR / "manifest.json") != manifest["prior_manifest_sha256"]:
        raise ValueError("Prior experiment drift")
    if base.tree_manifest(OUT / "code/src/migloop") != manifest["code"]:
        raise ValueError("Frozen code drift")
    if base.tree_manifest(manifest["pool"]["pool"])["content_digest"] != manifest["pool"]["content_digest"]:
        raise ValueError("Source pool drift")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify", "run"))
    mode = parser.parse_args().mode
    previous = load_previous()
    base = previous.load()
    old = previous.verify(base)
    if mode == "prepare":
        print(json.dumps(prepare(base, old), ensure_ascii=False), flush=True)
        return
    manifest = verify(base)
    if mode == "verify":
        print(json.dumps({"verified": True, "model_calls": 0}), flush=True)
        return
    print(json.dumps({"event": "start", "model": manifest["model"],
                      "effort": manifest["effort"], "sessions": 1}), flush=True)
    metrics = base.RAW.launch(manifest["case"]["pool"], OUT / "runs/inquiry/rep1",
                              (OUT / "prompt.md").read_bytes().decode("utf-8"),
                              base.read(OUT / "settings.json"), manifest["timeout_seconds"])
    verify(base)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
