"""Published skills run singly with site-packages/PYTHONPATH disabled, offline."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILLS / "migloop-memory-maintain/scripts"))
BUILDER = SKILLS / "migloop-memory-maintain/scripts/build_bundle.py"
spec = importlib.util.spec_from_file_location("self_contained_builder", BUILDER)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture(scope="module")
def release(tmp_path_factory):
    root = tmp_path_factory.mktemp("self-contained")
    output = root / "release"
    builder.build(SKILLS, output)
    return output


def only_skill(release, name, destination):
    result = destination / name
    shutil.copytree(release / name, result)
    return result


def run(skill, command, *args, ok=True):
    env = dict(os.environ, PYTHONPATH=str(skill.parent / "unavailable-source"), PYTHONNOUSERSITE="1")
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-X", "utf8",
                             str(skill / "scripts" / command), *map(str, args)],
                            cwd=skill.parent, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if ok:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0, result.stdout
    return result


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.fixture(params=["claude", "codex"])
def investigation(tmp_path, release, request):
    triage = only_skill(release, "migloop-repair-triage", tmp_path / "triage-alone")
    cards = only_skill(release, "migloop-build-cards", tmp_path / "cards-alone")
    pool = tmp_path / "pool"
    pool.mkdir()
    def row(at, actor, content):
        return {"type": "assistant", "sessionId": "synthetic-session", "agentId": actor,
                "cwd": "/app", "timestamp": f"2026-01-01T00:00:{at:02d}Z", "message": {"content": [content]}}
    def use(identity, name, **args):
        return {"type": "tool_use", "id": identity, "name": name, "input": args}
    def receipt(identity, value="ok"):
        return {"type": "tool_result", "tool_use_id": identity, "content": value}
    data = {
        "worker.jsonl": [row(1, "worker", use("read", "Read", file_path="/app/spec.md")),
                         row(2, "worker", receipt("read", "Required gap: 4dp.")),
                         row(3, "worker", use("write", "Write", file_path="/app/Page.ets", content="gap = 8")),
                         row(4, "worker", receipt("write"))],
        "repair.jsonl": [row(6, "repair", use("fix", "Edit", file_path="/app/Page.ets", old_string="gap = 8", new_string="gap = 4")),
                         row(7, "repair", receipt("fix"))]}
    for name, rows in data.items():
        if request.param == "codex":
            converted = [{"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z",
                          "payload": {"id": name.removesuffix(".jsonl"), "cwd": "/app", "cli_version": "synthetic"}}]
            for original in rows:
                block = original["message"]["content"][0]
                if block["type"] == "tool_use":
                    payload = {"type": "function_call", "call_id": block["id"], "name": block["name"],
                               "arguments": json.dumps(block["input"])}
                else:
                    payload = {"type": "function_call_output", "call_id": block["tool_use_id"],
                               "output": block["content"], "exit_code": 0}
                converted.append({"type": "response_item", "timestamp": original["timestamp"], "payload": payload})
            rows = converted
        (pool / name).write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    meta = tmp_path / "metadata.json"
    run(triage, "triage.py", "metadata", "--pool", pool, "--out", meta)
    scope = {"materials": [str(pool)], "project_roots": ["/app"],
             "generation_end": "2026-01-01T00:00:05Z", "observation_end": "2026-01-01T00:00:10Z"}
    issues = [{"title": name, "changes": [{"files": ["/app/Page.ets"], "change": "Synthetic fixture", "evidence": ["repair.jsonl:L1"]}]}
              for name in ("synthetic-one", "synthetic-two")]
    tasks = tmp_path / "tasks.yaml"
    dump(tasks, {"schema": "migloop-repair-triage/1", "scope": scope, "issues": issues})
    jobs = tmp_path / "jobs"
    run(triage, "triage.py", "dispatch", "--tasks", tasks, "--metadata", meta, "--out", jobs)
    manifest = json.loads((jobs / "jobs.json").read_text(encoding="utf-8"))
    graph = {"target": {"key": "/app/Page.ets", "since": scope["generation_end"], "at": scope["observation_end"]},
             "summary": "Synthetic input/output discrepancy", "recommendations": ["Compare the given value"],
             "nodes": [{"key": "/app/spec.md", "at": "2026-01-01T00:00:02Z", "reason": "Synthetic correct input"},
                       {"key": "worker.jsonl", "at": "2026-01-01T00:00:04Z", "problem": True, "reason": "Synthetic wrong output"}],
             "edges": [{"from": 1, "to": 2}, {"from": 2, "to": "target"}]}
    draft = {"title": "Synthetic test, not a real migration", "when": "implementation", "description": "specified value",
             "summary": "Input says 4, output says 8", "recommendations": ["Compare the value"], "unknown": [], "graphs": [graph]}
    path = tmp_path / "draft.yaml"
    dump(path, draft)
    return {"cards": cards, "pool": pool, "root": tmp_path, "draft": path, "value": draft,
            "jobs": [Path(j["job"]) for j in manifest["jobs"]]}


def test_solo_skill_builds_checks_and_reuses_shared_index(investigation):
    x = investigation
    first = json.loads(run(x["cards"], "cases.py", "prepare", "--job", x["jobs"][0]).stdout)
    second = json.loads(run(x["cards"], "cases.py", "prepare", "--job", x["jobs"][1]).stdout)
    assert first["reused"] is False and second["reused"] is True and first["db"] == second["db"]
    output = x["root"] / "case.json"
    checked = json.loads(run(x["cards"], "cases.py", "pack", "--job", x["jobs"][0], "--draft", x["draft"], "--out", output).stdout)
    receipt = checked["validation"]["graph_checks"][0]["receipt"]
    assert checked["validation"]["graph_check"] == "performed"
    assert receipt["mechanical_status"] == "valid" and receipt["path_status"] == "complete"
    assert checked["index"]["db"] == first["db"] and checked["index"]["reused"]
    assert len(checked["validation"]["kernel_sha256"]) == 64
    assert checked["validation"]["causal_correctness"] == "not_certified"
    request = x["root"] / "query.yaml"
    dump(request, [{"op": "catalog", "kind": "file", "q": "Page.ets"}])
    assert "Page.ets" in run(x["cards"], "cases.py", "query", "--job", x["jobs"][0], "--request", request).stdout


def test_pack_automatically_prepares_and_uses_exact_source_kernel(investigation):
    x = investigation
    checked = json.loads(run(x["cards"], "cases.py", "pack", "--job", x["jobs"][0], "--draft", x["draft"],
                             "--out", x["root"] / "auto.json").stdout)
    assert checked["index"]["reused"] is False
    from memorylib.inquiry_runtime import kernel
    assert checked["validation"]["kernel_sha256"] == kernel()[-1]
    from memorylib.cases import pack
    source = pack(x["jobs"][0], x["draft"], x["root"] / "source.json")
    a = checked["validation"]["graph_checks"][0]["receipt"]
    b = source["validation"]["graph_checks"][0]["receipt"]
    for key in ("mechanical_status", "path_status", "issues", "delivery"):
        assert a[key] == b[key]
    generated = json.loads((x["root"] / "auto.json").read_text(encoding="utf-8"))
    canonical = json.loads((x["root"] / "source.json").read_text(encoding="utf-8"))
    assert generated["graph_evidence"] == canonical["graph_evidence"]


def test_bad_edge_is_not_certified_and_source_change_is_rejected(investigation):
    x = investigation
    draft = copy.deepcopy(x["value"])
    draft["graphs"][0]["nodes"][0]["key"] = "/app/never-read.md"
    invalid = x["root"] / "invalid.yaml"
    dump(invalid, draft)
    checked = json.loads(run(x["cards"], "cases.py", "pack", "--job", x["jobs"][0], "--draft", invalid,
                             "--out", x["root"] / "invalid.json", ok=False).stdout)
    receipt = checked["graph_checks"][0]["receipt"]
    assert checked["card"] is None and not (x["root"] / "invalid.json").exists()
    assert receipt.get("mechanical_status") != "valid"
    assert receipt.get("status") == "rejected" or receipt.get("unverified_edges") or receipt.get("issues")
    source = x["pool"] / "worker.jsonl"
    source.write_text(source.read_text(encoding="utf-8") + "\n{}", encoding="utf-8")
    error = run(x["cards"], "cases.py", "prepare", "--job", x["jobs"][0], ok=False)
    assert "Transcript changed" in error.stderr


def test_draft_only_bypass_removed_and_runtime_damage_fails_closed(investigation):
    x = investigation
    error = run(x["cards"], "cases.py", "pack", "--job", x["jobs"][0], "--draft", x["draft"],
                "--out", x["root"] / "draft-only.json", "--draft-only", ok=False)
    assert "unrecognized arguments" in error.stderr
    assert not (x["root"] / "draft-only.json").exists()
    core = x["cards"] / "scripts/_runtime/migloop/inquiry/store.py"
    core.write_text(core.read_text(encoding="utf-8") + "\n# accidental local patch\n", encoding="utf-8")
    error = run(x["cards"], "cases.py", "prepare", "--job", x["jobs"][0], ok=False)
    assert "Skill package changed" in error.stderr


def test_maintain_and_recall_work_with_no_sibling_skills(release, tmp_path):
    maintain = only_skill(release, "migloop-memory-maintain", tmp_path / "maintain-only")
    recall = only_skill(release, "migloop-memory-recall", tmp_path / "recall-only")
    store = tmp_path / "store"
    assert json.loads(run(maintain, "memory.py", "init", "--store", store).stdout)["revision"]
    assert json.loads(run(maintain, "recall.py", "browse", "--store", store).stdout)["total"] == 0
    assert json.loads(run(recall, "recall.py", "browse", "--store", store).stdout)["total"] == 0
    plan = tmp_path / "plan.yaml"
    revision = json.loads(run(maintain, "memory.py", "snapshot", "--store", store).stdout)["revision"]
    dump(plan, {"base_revision": revision, "upsert": [], "retire": [], "topic_descriptions": {}})
    run(maintain, "memory.py", "apply", "--store", store, "--plan", plan)
    reading = tmp_path / "reading"
    run(maintain, "memory.py", "export", "--store", store, "--out", reading)
    assert (reading / "index.md").exists()
    project = tmp_path / "project"
    project.mkdir()
    run(recall, "claude_hook.py", "install", "--project", project, "--memory", reading)
    assert (project / ".claude/hooks/migloop_memory.py").is_file()
    assert not (maintain / "scripts/_runtime/migloop").exists()
    assert not (recall / "scripts/_runtime/migloop").exists()


def test_release_has_no_ui_native_extensions_or_session_artifacts(release):
    for skill in builder.NAMES:
        package = release / skill
        manifest = json.loads((package / "package-manifest.json").read_text(encoding="utf-8"))
        assert manifest["inquiry_included"] == (skill == "migloop-build-cards")
        assert manifest["dependencies"]["PyYAML"] == "6.0.3"
        assert (package / "licenses/PyYAML-LICENSE.txt").is_file()
        assert not any(p.suffix in (".html", ".js", ".pyd", ".so", ".sqlite", ".jsonl", ".pyc") for p in package.rglob("*") if p.is_file())
