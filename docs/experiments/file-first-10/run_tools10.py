"""Paired frozen tools group. prepare/verify/smoke are offline; only run calls a model.

Reuses the unchanged raw launch/command/native parser. No retry, fallback,
schema-repair turn, reference injection or global Codex configuration changes.
"""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_PYTHON = Path("C:/Users/hongy/projects/migbot-elite/.venv/Scripts/python.exe")
ENABLED_TOOLS = ("guide", "batch", "changes", "expand", "check", "index", "sessions")


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RAW = _module(HERE / "run_raw10.py", "tools10_unchanged_raw")
MODEL, EFFORT = RAW.MODEL, RAW.EFFORT
sha, read, save, now = RAW.sha, RAW.read, RAW.save, RAW.now


def _inside(path, root):
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def _time(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Explicit timezone required")
    return stamp.astimezone(timezone.utc)


def tree_manifest(root):
    """Same canonical inventory algorithm as the frozen raw native parser."""
    return RAW.parser().inventory(Path(root))


def _all_files(root):
    """Pool/snapshot guards must not ignore new pyc/cache files or links."""
    root = Path(root)
    names = []
    for path in root.rglob("*"):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Frozen inventory does not accept links: " + str(path))
        if path.is_file():
            names.append(path.relative_to(root).as_posix())
    return sorted(names)


def _root_start(path):
    # CC may start with last-prompt metadata without a timestamp. Match the
    # service/crosschain first-timestamped-record rule, not filesystem mtime.
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("timestamp"):
                try:
                    stamp = _time(row["timestamp"])
                except (ValueError, TypeError):
                    continue
                return {"path": str(Path(path).resolve()), "line": number,
                        "timestamp": row["timestamp"], "normalized_time": stamp.isoformat()}
    raise ValueError("Pool root has no valid explicit timestamp: " + str(path))


def verify_pools(raw_manifest):
    """Verify the old COMPLETE manifests, not only raw's 228 JSONLs."""
    pools = []
    for pool_name in sorted({case["pool"] for case in raw_manifest["cases"]}):
        pool = Path(pool_name).resolve()
        old_path = pool.parent / "pool-manifest.json"
        old = read(old_path)
        current = tree_manifest(pool)
        if (old.get("algorithm") != "sha256" or current["entries"] != old.get("entries")
                or current["content_digest"] != old.get("content_digest")
                or _all_files(pool) != sorted(item["path"] for item in old.get("entries", []))):
            raise ValueError("Complete pool/sidecar manifest drift: " + str(pool))
        # The raw source set must be exactly the JSONL subset of this pool.
        frozen_jsonl = {str(Path(x["path"]).resolve()): x["sha256"] for x in raw_manifest["source_files"]
                        if _inside(x["path"], pool)}
        actual_jsonl = {str((pool / x["path"]).resolve()): x["sha256"] for x in current["entries"]
                        if x["path"].endswith(".jsonl")}
        if actual_jsonl != frozen_jsonl:
            raise ValueError("Raw JSONL subset differs from complete pool manifest")
        roots = sorted(pool / entry["path"] for entry in old["entries"]
                       if Path(entry["path"]).parent == Path(".") and entry["path"].endswith(".jsonl"))
        dated = []
        for path in roots:
            start = _root_start(path)
            dated.append((_time(start["timestamp"]), str(path.resolve()), start))
        if not dated:
            raise ValueError("Pool has no timestamped native roots")
        dated.sort()
        pools.append({"pool": str(pool), "manifest": str(old_path), "manifest_sha256": sha(old_path),
                      "content_digest": current["content_digest"], "file_count": len(current["entries"]),
                      "jsonl_count": len(actual_jsonl), "roots": [path for _, path, _ in dated],
                      "root_starts": [start for _, _, start in dated],
                      "anchor": dated[-1][1]})
    if len(pools) != 3 or sum(p["file_count"] for p in pools) != 436 \
            or sum(p["jsonl_count"] for p in pools) != 228:
        raise ValueError("Expected the same three pools: 228 JSONLs + 208 sidecars = 436 files")
    return pools


def _entry_code(code, module, function):
    # -I ignores inherited Python paths/user site. The one explicitly inserted
    # package path is the frozen copy, never the editable checkout.
    return f"import sys; sys.path.insert(0, {(Path(code)/'src').as_posix()!r}); from {module} import {function}; {function}()"


def settings(raw_settings, code, python, pool):
    config = deepcopy(raw_settings)
    if config.get("model_reasoning_effort") != EFFORT or not config.get("features.shell_tool"):
        raise ValueError("Unexpected raw baseline settings")
    config["features.shell_tool"] = False
    config["mcp_servers"] = {"migloop": {
        "command": str(Path(python).resolve()),
        "args": ["-I", "-B", "-X", "utf8", "-c", _entry_code(code, "migloop.mcp_server", "main")],
        "env": {"MIGLOOP_FROZEN_POOL": pool["pool"], "MIGLOOP_FROZEN_ANCHOR": pool["anchor"],
                "MIGLOOP_FROZEN_ROOTS": json.dumps(pool["roots"]),
                "MIGLOOP_VERDICT_VERSION": "3", "MIGLOOP_FINAL_MODE": "document"},
        "required": True, "startup_timeout_sec": 120, "tool_timeout_sec": 180,
        "enabled_tools": list(ENABLED_TOOLS),
    }}
    return config


def prompt(raw_prompt, sid):
    # Preserve EVERY raw byte as the prefix, including its shell-specific tail.
    # Only the instrument and final-document representation differ in this arm.
    return raw_prompt + ("\n\n工具组操作与提交说明（只替换上文末段的shell操作面和最终表示格式；调查问题、材料和时间边界不变）：\n"
        f"本轮shell已禁用；仅使用migloop MCP，所有调用的sid为：{sid}\n"
        "可先guide(topic=\"time\")了解接口。通过batch自由并行file/agent/search/diff/blame/events/changes/expand，"
        "不填旧v/via；scope与分页按返回继承。这里不指定调查顺序、缺陷数量或预期答案。\n"
        "最终提交完整migloop-verdict/3 YAML或JSON文稿，放在一个yaml或json代码块中，可带一小段摘要；用guide(topic=\"verdict\")查看字段模板，"
        "不要提交migloop-verdict-ref，也不要只说已完成。保持中文解释与原始证据定位。"
        "可以自行调用check核对草稿，但机械核验不是归因正确证明；没有强制格式修复轮、自动重跑或模型回退。"
        "结构化输出的token与耗时全部计入本轮成本，不需要再复制同义散文。\n")


def prepare(out, baseline, *, python=DEFAULT_PYTHON, source=REPO, dev_smoke=False):
    started = time.perf_counter()
    out, baseline, source, python = [Path(p).resolve() for p in (out, baseline, source, python)]
    raw = RAW.verify_manifest(baseline)
    if (raw.get("model"), raw.get("effort"), raw.get("repetitions"), raw.get("concurrency"),
            raw.get("timeout_seconds"), len(raw.get("cases", []))) != (MODEL, EFFORT, 2, 2, 1800, 10):
        raise ValueError("Paired model/tasks/repetitions/concurrency/timeout changed")
    if len({c["id"] for c in raw["cases"]}) != 10 or len({(c["pool"], c["file"]) for c in raw["cases"]}) != 10:
        raise ValueError("Expected ten distinct raw cases/files")
    if out.exists() or _inside(out, baseline) or _inside(out, source) \
            or any(_inside(out, c["pool"]) or _inside(c["pool"], out) for c in raw["cases"]):
        raise ValueError("Tools output must be new and separate from raw baseline, source and pools")
    if not python.is_file() or not (source / "src/migloop").is_dir():
        raise ValueError("Explicit Python runtime and source package are required")
    pools = verify_pools(raw)
    before = tree_manifest(source / "src/migloop")
    raw_settings = read(baseline / "runtime-settings.json")
    out.mkdir(parents=True)
    package = out / "code/src/migloop"
    shutil.copytree(source / "src/migloop", package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    if tree_manifest(package) != before or tree_manifest(source / "src/migloop") != before:
        raise ValueError("Source changed during freeze; no runnable manifest created")
    save(out / "code-manifest.json", before)
    (out / "tasks").mkdir()
    (out / "settings").mkdir()
    cases = []
    by_pool = {p["pool"]: p for p in pools}
    for original in raw["cases"]:
        case = deepcopy(original)
        pooled = by_pool[str(Path(case["pool"]).resolve())]
        case.update(pool=pooled["pool"], sid=pooled["anchor"], roots=pooled["roots"])
        raw_path = baseline / original["prompt"]
        # UTF-8 bytes are not silently newline-normalized when copied as prefix.
        raw_text = raw_path.read_bytes().decode("utf-8")
        bounds = []
        for label in ("生成结束", "观察截止"):
            match = re.search(r"(?m)^" + label + r"：([^，\r\n]+)", raw_text)
            if match is None:
                raise ValueError("Raw task lacks explicit time boundary: " + label)
            _time(match[1])
            bounds.append(match[1])
        case.update(raw_prompt=str(raw_path), raw_prompt_sha256=sha(raw_path),
                    generation_end=bounds[0], observation_end=bounds[1],
                    prompt=f"tasks/{case['id']}.md", settings=f"settings/{case['id']}.json")
        (out / case["prompt"]).write_bytes(prompt(raw_text, case["sid"]).encode("utf-8"))
        save(out / case["settings"], settings(raw_settings, out / "code", python, pooled))
        cases.append(case)
    artifacts = [{"path": p.relative_to(out).as_posix(), "sha256": sha(p)}
                 for p in sorted(out.rglob("*")) if p.is_file()]
    manifest = {"schema": "migloop-file-first-tools10-baseline/1",
                "status": "frozen_dev_smoke_only" if dev_smoke else "frozen_ready_for_tools",
                "frozen_at": now(), "model": MODEL, "effort": EFFORT, "repetitions": 2,
                "concurrency": 2, "timeout_seconds": 1800, "cases": cases, "pools": pools,
                "raw_base": str(baseline), "raw_manifest_sha256": sha(baseline / "manifest.json"),
                "raw_runner_sha256": sha(HERE / "run_raw10.py"), "parser_sha256": sha(RAW.OLD_RUNNER),
                "runner_sha256": sha(Path(__file__)), "source": str(source),
                "code_digest": before["content_digest"], "artifacts": artifacts,
                "python": str(python), "python_sha256": sha(python),
                "prepare_elapsed_seconds": time.perf_counter() - started,
                "automatic_retry": False, "format_repair": False, "final_mode": "document",
                "cost_scope": "all investigator input/output includes schema3; preparation and postprocessing reported separately"}
    save(out / "manifest.json", manifest)
    return {"out": str(out), "status": manifest["status"], "manifest_sha256": sha(out / "manifest.json"),
            "code_digest": manifest["code_digest"], "pool_files": sum(p["file_count"] for p in pools),
            "model_started": False}


def verify(out):
    out = Path(out).resolve()
    manifest = read(out / "manifest.json")
    if manifest.get("status") not in ("frozen_ready_for_tools", "frozen_dev_smoke_only"):
        raise ValueError("Tools manifest is not frozen")
    baseline = Path(manifest["raw_base"])
    raw = RAW.verify_manifest(baseline)
    for key, expected in (("model", MODEL), ("effort", EFFORT), ("repetitions", 2),
                          ("concurrency", 2), ("timeout_seconds", 1800), ("final_mode", "document"),
                          ("automatic_retry", False), ("format_repair", False)):
        if manifest.get(key) != expected:
            raise ValueError("Paired runtime condition drift: " + key)
    if sha(baseline / "manifest.json") != manifest["raw_manifest_sha256"]:
        raise ValueError("Raw baseline manifest drift")
    if sha(Path(__file__)) != manifest["runner_sha256"] or sha(HERE / "run_raw10.py") != manifest["raw_runner_sha256"] \
            or sha(RAW.OLD_RUNNER) != manifest["parser_sha256"]:
        raise ValueError("Runner/parser drift")
    if sha(manifest["python"]) != manifest["python_sha256"]:
        raise ValueError("Python runtime changed")
    for item in manifest["artifacts"]:
        if sha(out / item["path"]) != item["sha256"]:
            raise ValueError("Frozen tools artifact drift: " + item["path"])
    code_manifest = read(out / "code-manifest.json")
    if (tree_manifest(out / "code/src/migloop") != code_manifest or
            _all_files(out / "code/src/migloop") != sorted(item["path"] for item in code_manifest["entries"])
            or manifest["code_digest"] != code_manifest["content_digest"]):
        raise ValueError("Frozen package inventory drift, including extra files")
    if verify_pools(raw) != manifest["pools"]:
        raise ValueError("Complete pool manifest or root registry changed")
    if [(c["id"], c["file"], str(Path(c["pool"]).resolve())) for c in manifest["cases"]] != \
            [(c["id"], c["file"], str(Path(c["pool"]).resolve())) for c in raw["cases"]]:
        raise ValueError("Paired cases changed")
    by_pool = {p["pool"]: p for p in manifest["pools"]}
    raw_settings = read(baseline / "runtime-settings.json")
    for case, original in zip(manifest["cases"], raw["cases"]):
        pool = by_pool[case["pool"]]
        raw_path = baseline / original["prompt"]
        if (case["prompt"] != f"tasks/{case['id']}.md" or case["settings"] != f"settings/{case['id']}.json"
                or case["sid"] != pool["anchor"] or case["roots"] != pool["roots"]
                or case["raw_prompt_sha256"] != sha(raw_path)):
            raise ValueError("Case launch binding drift")
        if (out / case["prompt"]).read_bytes() != prompt(raw_path.read_bytes().decode("utf-8"), case["sid"]).encode("utf-8"):
            raise ValueError("Paired task text drift")
        if read(out / case["settings"]) != settings(raw_settings, out / "code", manifest["python"], pool):
            raise ValueError("Paired runtime settings drift")
    return manifest


def _child_env(server):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MIGLOOP_") and k != "PYTHONPATH"}
    env.update(server["env"])
    return env


# Runs once after the real final answer, in the frozen package. It never asks a
# model to fix malformed output, nor interprets cached check data as submission.
POSTPROCESS = r'''
import hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from migloop import atoms, verdict, verdict_v3, service, probe, via, investigation, draft_check
run, sid = Path(sys.argv[2]), sys.argv[3]
expected = json.loads(sys.argv[4])
started = time.perf_counter()
report_path = run / "report.md"
report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
ledger = service.session_ledger(sid)
identity = atoms.ledger_identity(ledger)
calls = probe._transcript_calls(str(run)) or []
trace_identity = via.trace_identity(ledger, calls, {})
loaded = verdict.load_block(report)
errors = list(loaded["errors"])
if loaded["data"] is not None and loaded["data"].get("schema") != verdict_v3.SCHEMA:
    errors.append("This arm requires the actual inline migloop-verdict/3 final document; no reference or repair")
if loaded["data"] is not None and not errors:
    target = loaded["data"]["target"]
    actual_file = target["file"].replace("\\", "/")
    task_file = expected["file"].replace("\\", "/")
    if actual_file != task_file and not actual_file.endswith("/" + task_file):
        errors.append("Final target differs from the frozen raw task file")
    def stamp(value):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    for field, source in (("at", "observation_end"), ("since_ts", "generation_end")):
        if target.get(field) is None or stamp(target[field]) != stamp(expected[source]):
            errors.append("Final target." + field + " differs from the frozen raw task boundary")
built = verdict_v3.build(ledger, loaded["data"] if not errors else None, errors,
    {"raw": loaded["raw"], "harness_identity": identity, "trace_identity": trace_identity})
result = {"schema": "migloop-tools10-final-verification/1", **loaded, "errors": errors,
          "harness_identity": identity, "trace_identity": trace_identity, "verification": built,
          "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest() if report_path.exists() else None,
          "semantic_checked": False, "format_repair": False,
          "postprocess_elapsed_seconds": time.perf_counter() - started}
with (run / "verdict.json").open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
with (run / "query-trace.json").open("x", encoding="utf-8") as handle:
    json.dump(investigation.project_trace(ledger, calls), handle, ensure_ascii=False, indent=2)
print(json.dumps({"errors": errors, "identity_bound": built["identity"]["bound"],
                  "semantic_checked": False, "native_calls": len(calls)}, ensure_ascii=False))
'''


def postprocess(out, manifest, case, run):
    config = read(Path(out) / case["settings"])
    server = config["mcp_servers"]["migloop"]
    started = time.perf_counter()
    cmd = [manifest["python"], "-I", "-B", "-X", "utf8", "-c", POSTPROCESS,
           str(Path(out) / "code/src"), str(run), case["sid"],
           json.dumps({key: case[key] for key in ("file", "generation_end", "observation_end")})]
    with (run / "postprocess.stdout.txt").open("xb") as stdout, (run / "postprocess.stderr.txt").open("xb") as stderr:
        try:
            kwargs = {"cwd": case["pool"], "env": _child_env(server), "stdout": stdout, "stderr": stderr,
                      "timeout": 600, "check": False}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(cmd, **kwargs)
            status = "completed" if result.returncode == 0 else "error"
        except (OSError, subprocess.TimeoutExpired) as error:
            status = "error"
            stderr.write(repr(error).encode("utf-8"))
    if not (run / "verdict.json").exists():
        save(run / "verdict.json", {"schema": "migloop-tools10-final-verification/1", "data": None,
             "errors": ["Frozen verifier failed; see postprocess.stderr.txt"], "semantic_checked": False,
             "format_repair": False})
    return {"status": status, "elapsed_seconds": time.perf_counter() - started,
            "verdict_sha256": sha(run / "verdict.json"), "model_calls": 0}


def launch_case(out, manifest, case, rep):
    out = Path(out).resolve()
    run = out / "runs" / case["id"] / f"rep{rep}"
    started = time.perf_counter()
    metric = RAW.launch(case["pool"], run, (out / case["prompt"]).read_bytes().decode("utf-8"),
                        read(out / case["settings"]), manifest["timeout_seconds"])
    verification = postprocess(out, manifest, case, run)
    # Preserve raw's exact first metrics document; expose system-inclusive costs
    # separately without discounting structured final-output tokens.
    (run / "metrics.json").rename(run / "raw-launch-metrics.json")
    metric = {**metric, "condition": "tools", "final_mode": "document", "format_repair": False,
              "investigator_elapsed_seconds": metric["elapsed_seconds"], "postprocess": verification,
              "system_elapsed_seconds": time.perf_counter() - started,
              "code_digest": manifest["code_digest"], "raw_manifest_sha256": manifest["raw_manifest_sha256"],
              "tools_manifest_sha256": sha(out / "manifest.json"),
              "structured_output_cost_included": True}
    save(run / "metrics.json", metric)
    return metric


REGISTRY_SMOKE = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from migloop import atoms, service, transcript_store, investigation
ledger = service.session_ledger(sys.argv[2])
registry = transcript_store.sources(ledger)
print(json.dumps({"source_paths": sorted(registry), "source_count": len(registry),
                  "ledger": atoms.ledger_identity(ledger),
                  "scope": investigation.scope(ledger, "file", sys.argv[3], sys.argv[4])}, ensure_ascii=False))
'''


def registry_smoke(out, manifest, case, pool):
    server = read(Path(out) / case["settings"])["mcp_servers"]["migloop"]
    cmd = [manifest["python"], "-I", "-B", "-X", "utf8", "-c", REGISTRY_SMOKE, str(Path(out) / "code/src"),
           case["sid"], case["file"], case["observation_end"]]
    kwargs = {"cwd": case["pool"], "env": _child_env(server), "capture_output": True,
              "timeout": 300, "check": False}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(cmd, **kwargs)
    if result.returncode:
        raise ValueError("Frozen registry smoke failed: " + result.stderr.decode("utf-8", errors="replace")[-2000:])
    data = json.loads(result.stdout.decode("utf-8"))
    expected = {os.path.normcase(str((Path(pool["pool"]) / row["path"]).resolve()))
                for row in read(pool["manifest"])["entries"] if row["path"].endswith(".jsonl")}
    observed = {os.path.normcase(str(Path(path).resolve())) for path in data["source_paths"]}
    data["matches"] = observed == expected and data["source_count"] == pool["jsonl_count"]
    data["expected_count"] = pool["jsonl_count"]
    data["missing"] = sorted(expected - observed)
    data["extra"] = sorted(observed - expected)
    return data


def _batch_smoke_check(text, request, registry):
    """A non-error MCP envelope can still contain deferred/error batch items."""
    body, separator, tail = text.rpartition("\nMIGLOOP_INVESTIGATION_RECEIPT ")
    if not separator:
        return False
    def digest(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()
    try:
        data, receipt = json.loads(body), json.loads(tail)
        item, = data["items"]
        return (data["schema"] == "migloop-investigation-batch/1" and item["status"] == "ok"
                and item["tool"] == "file" and item["scope"] == registry["scope"]
                and item["data"]["schema"] == "migloop-time-view/1"
                and item["data"]["scope"] == registry["scope"]
                and item["data"]["source_count"] == registry["expected_count"]
                and receipt["schema"] == "migloop-investigation-receipt/1"
                and receipt["ledger"] == data["ledger"] == registry["ledger"]
                and receipt["body_sha256"] == digest(body)
                and receipt["request_sha256"] == digest({k: v for k, v in request.items() if k != "sid"}))
    except (ValueError, KeyError, TypeError):
        return False


async def _smoke(server, case, registry):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    parameters = StdioServerParameters(command=server["command"], args=server["args"],
        env=_child_env(server), cwd=case["pool"])
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            advertised = {t.name for t in (await session.list_tools()).tools}
            guide = await session.call_tool("guide", {"topic": "time"})
            # A neutral native query tests frozen pool loading as well as startup.
            request = {"sid": case["sid"], "requests": [
                {"tool": "file", "args": {"path": case["file"], "at": case["observation_end"], "limit": 1}}], "max_chars": 12000}
            batch = await session.call_tool("batch", request)
            text = "\n".join(c.text for c in batch.content if hasattr(c, "text"))
            content_ok = _batch_smoke_check(text, request, registry)
            return {"passed": registry["matches"] and content_ok and set(ENABLED_TOOLS).issubset(advertised)
                              and not guide.isError and not batch.isError,
                    "batch_content_verified": content_ok,
                    "advertised_tools": sorted(advertised), "enabled_tools": list(ENABLED_TOOLS),
                    "guide": [c.text for c in guide.content if hasattr(c, "text")],
                    "batch": [c.text for c in batch.content if hasattr(c, "text")],
                    "model_calls": 0, "limit": "Direct MCP smoke; not a Codex model/allowlist enforcement test"}


def smoke(out):
    out = Path(out).resolve()
    manifest = verify(out)
    if (out / "mcp-smoke.json").exists():
        raise FileExistsError("No automatic smoke overwrite")
    started = time.perf_counter()
    pools = []
    for pool in manifest["pools"]:
        case = next(c for c in manifest["cases"] if c["pool"] == pool["pool"])
        print(json.dumps({"event": "mcp_smoke_start", "pool": pool["pool"], "time": now(),
                          "model_calls": 0}, ensure_ascii=False), flush=True)
        try:
            registry = registry_smoke(out, manifest, case, pool)
            print(json.dumps({"event": "mcp_smoke_registry", "pool": pool["pool"],
                              "observed": registry["source_count"], "expected": registry["expected_count"],
                              "matches": registry["matches"], "time": now()}, ensure_ascii=False), flush=True)
            server = read(out / case["settings"])["mcp_servers"]["migloop"]
            checked = asyncio.run(asyncio.wait_for(_smoke(server, case, registry), timeout=300))
            pools.append({"pool": pool["pool"], "registry": registry, **checked})
        except Exception as error:
            pools.append({"pool": pool["pool"], "passed": False, "error": repr(error), "model_calls": 0})
        print(json.dumps({"event": "mcp_smoke_finish", "pool": pool["pool"], "passed": pools[-1]["passed"],
                          "time": now(), "error": pools[-1].get("error")}, ensure_ascii=False), flush=True)
    result = {"passed": len(pools) == 3 and all(p["passed"] for p in pools), "pools": pools,
              "model_calls": 0, "elapsed_seconds": time.perf_counter() - started,
              "code_digest": manifest["code_digest"], "tools_manifest_sha256": sha(out / "manifest.json")}
    save(out / "mcp-smoke.json", result)
    verify(out)
    return {"passed": result["passed"], "model_calls": 0, "out": str(out)}


def _require_smoke(out, manifest):
    path = Path(out) / "mcp-smoke.json"
    if not path.exists():
        raise ValueError("Run requires the offline three-pool MCP smoke")
    result = read(path)
    if (not result.get("passed") or result.get("code_digest") != manifest["code_digest"]
            or result.get("tools_manifest_sha256") != sha(Path(out) / "manifest.json")
            or len(result.get("pools", [])) != 3
            or {p.get("pool") for p in result.get("pools", [])} != {p["pool"] for p in manifest["pools"]}
            or any(not p.get("passed") or not p.get("batch_content_verified") or not (p.get("registry") or {}).get("matches")
                   for p in result.get("pools", []))):
        raise ValueError("Three-pool MCP/source registry smoke failed or drifted")


def run_queue(out):
    out = Path(out).resolve()
    manifest = verify(out)
    if manifest["status"] != "frozen_ready_for_tools":
        raise ValueError("Development smoke snapshot cannot launch investigators; freeze a new formal arm")
    jobs = [(case, rep) for rep in (1, 2) for case in manifest["cases"]]
    if (out / "queue.jsonl").exists() or any((out / "runs" / c["id"] / f"rep{r}").exists() for c, r in jobs):
        raise FileExistsError("Existing run/queue; no overwrite, resume, retry or fallback")
    _require_smoke(out, manifest)
    stopped = False
    with (out / "queue.jsonl").open("x", encoding="utf-8", buffering=1) as journal:
        def emit(value):
            line = json.dumps({"time": now(), **value}, ensure_ascii=False)
            journal.write(line + "\n")
            print(line, flush=True)
        emit({"event": "start", "jobs": len(jobs), "concurrency": 2, "condition": "tools"})
        with ThreadPoolExecutor(max_workers=2) as executor:
            pending = {}
            while jobs or pending:
                while jobs and len(pending) < 2 and not stopped:
                    case, rep = jobs.pop(0)
                    emit({"event": "launch", "case": case["id"], "rep": rep})
                    pending[executor.submit(launch_case, out, manifest, case, rep)] = (case["id"], rep)
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for task in done:
                    case, rep = pending.pop(task)
                    try:
                        metric = task.result()
                    except Exception as error:
                        metric = {"status": "harness_error", "error": repr(error)}
                    emit({"event": "finish", "case": case, "rep": rep, **metric})
                    if (metric.get("status") not in ("completed", "timeout", "incomplete")
                            or metric.get("actual_models") != [MODEL] or metric.get("actual_effort") != EFFORT
                            or not metric.get("recording_complete") or not metric.get("host_skill_catalog_absent")
                            or (metric.get("postprocess") or {}).get("status") != "completed"):
                        stopped = True
                        emit({"event": "stop_scheduling", "reason": "infrastructure_or_identity_failure", "unstarted": len(jobs)})
            verify(out)
            emit({"event": "end", "status": "stopped" if stopped else "finished", "unstarted": len(jobs)})
    return {"out": str(out), "status": "stopped" if stopped else "finished"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("prepare", "verify", "smoke", "run"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    ap.add_argument("--source", type=Path, default=REPO)
    ap.add_argument("--dev-smoke", action="store_true", help="prepare a snapshot that cannot launch model runs")
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
