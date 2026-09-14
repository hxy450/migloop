"""One independent tree-completion fork of a model's own finished review.

prepare/verify/audit are offline; only run starts a model, without retries.
"""

import argparse
import importlib.util
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SKILL, PAIRED, AUDITOR = load("run_skill_case"), load("run_paired_review"), load("audit_paired_review")
BASE, RAW = SKILL.BASE, SKILL.BASE.RAW


def inherit_queries(source, target):
    """Append old query coordinates; keep the freshly parsed index facts."""
    for query in ("SELECT * FROM sources ORDER BY id", "SELECT ref,sha FROM records ORDER BY ref"):
        if source.execute(query).fetchall() != target.execute(query).fetchall():
            raise ValueError("Different source pools; cannot inherit query history")
    added = {}
    with target:
        for table, keys in (("handles", ["id"]), ("runs", ["id"]), ("frames", ["run", "offset"]), ("visible", ["run", "offset"])):
            schema = source.execute("PRAGMA table_info(" + table + ")").fetchall()
            if schema != target.execute("PRAGMA table_info(" + table + ")").fetchall():
                raise ValueError("Different history schema: " + table)
            columns, added[table] = [c[1] for c in schema], 0
            for row in source.execute("SELECT * FROM " + table + " ORDER BY rowid"):
                old = target.execute("SELECT * FROM " + table + " WHERE " + " AND ".join(k + "=?" for k in keys),
                                     [row[columns.index(k)] for k in keys]).fetchall()
                if old and any(existing != row for existing in old):
                    raise ValueError("History identity collision: " + table)
                if not old:
                    target.execute("INSERT INTO " + table + " VALUES (" + ",".join("?" for _ in row) + ")", row)
                    added[table] += 1
    return added


def prepare(out, review_root, identity):
    PAIRED.verify(review_root)
    parent = review_root / identity / "inquiry"
    metric = BASE.read(parent / "rep1/metrics.json")
    if not (metric["status"] == "completed" and metric["actual_models"] == [RAW.MODEL]
            and metric["actual_effort"] == "high" and metric["recording_complete"] and metric["report_present"]):
        raise ValueError("Parent must be a completed recorded Luna/high review")
    native = RAW.parser().find_codex_transcript(metric["session_id"])
    digest = BASE.sha(parent / "rep1/transcript.jsonl")
    if not native or BASE.sha(native) != digest or metric["transcript_sha256"] != digest:
        raise ValueError("Parent native history differs from frozen review")
    records = PAIRED.rows(native)
    finals = [p for p in PAIRED.messages(records) if p.get("role") == "assistant" and p.get("phase") == "final_answer"]
    if not finals or "\n".join(c.get("text", "") for c in finals[-1]["content"]).strip() != (parent / "rep1/report.md").read_text(encoding="utf-8").strip():
        raise ValueError("Review delta is not the parent's native final answer")
    SKILL.prepare(out, identity)
    shutil.copy2(out / "manifest.json", out / "prepare-manifest.json")
    m, workspace = BASE.read(out / "manifest.json"), out / "workspace"
    task = BASE.read(parent / "workspace/investigation.json")
    job = BASE.read(workspace / "investigation.json")
    if any(task[k] != job[k] for k in ("file", "pool", "generation_end", "observation_end")):
        raise ValueError("Review and tree task scopes differ")
    parent_db, snapshot = review_root / identity / "index.sqlite", out / "parent-index.sqlite"
    source_digest = BASE.sha(parent_db)
    with closing(sqlite3.connect(parent_db.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(snapshot)) as saved:
            source.backup(saved)
            with closing(sqlite3.connect(out / "index.sqlite")) as working:
                inherited = inherit_queries(saved, working)
    if BASE.sha(parent_db) != source_digest:
        raise ValueError("Parent index changed during readonly backup")
    inputs = {"initial-report.md": parent / "workspace/initial-report.md", "review-delta.md": parent / "rep1/report.md"}
    for name, source in inputs.items():
        shutil.copy2(source, workspace / name)
    shutil.copy2(native, out / "parent-native.jsonl")
    shutil.copy2(__file__, out / "completion-driver.py")
    prompt = ("使用 $migloop-investigate（.agents/skills/migloop-investigate/SKILL.md），基于你已完成的调查与复核，"
              "为 investigation.json 制作并审核可加载的时间证据树。本轮任务是构树收尾。"
              "完整以 UTF-8 读取 initial-report.md、review-delta.md 和技能参考；PowerShell 用 Get-Content -Encoding utf8。"
              "保留复核已证输入、输出偏差、停止边界及不确定性；只按新增原始证据纠正判断并说明。"
              "可用原始读取和 MCP 补核所需坐标，不要求重查全过程。原稿与复核稿保持不变。"
              "历史通过父线程引用继承，不保证在当前转录中重复全文。")
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    cli = RAW.command(workspace, BASE.read(out / "settings.json"))[0]
    files = [Path(__file__), Path(SKILL.__file__), Path(PAIRED.__file__), Path(AUDITOR.__file__), Path(SKILL.iteration.__file__),
             Path(BASE.__file__), Path(RAW.__file__), Path(RAW.OLD_RUNNER), Path(cli), Path(native), *inputs.values(),
             parent / "workspace/investigation.json", parent / "rep1/metrics.json", parent / "rep1/transcript.jsonl",
             out / "parent-native.jsonl", out / "completion-driver.py", out / "prepare-manifest.json", snapshot]
    m.update(workspace_inventory=BASE.tree_manifest(workspace), prompt_sha256=BASE.sha(out / "prompt.md"), timeout_seconds=1200,
             comparison_limit="Independent tree-fidelity follow-up; never merge into paired raw/inquiry review scores.")
    m["completion"] = {"review_root": str(review_root), "case": identity, "parent_session": metric["session_id"],
        "parent_sha256": digest, "parent_bytes": Path(native).stat().st_size,
        "parent_end_ordinal": records[-1]["ordinal"] + 1, "files": {str(p): BASE.sha(p) for p in files},
        "parent_index": {"source": str(parent_db), "source_sha256": source_digest,
                         "snapshot_sha256": BASE.sha(snapshot), "inherited": inherited,
                         "copy": "readonly snapshot; query history appended to fresh import, files/mentions/effects retained"},
        "history": "Paginated inherited parent reference; no claim of visible full-history duplication.",
        "inputs": {name: BASE.sha(source) for name, source in inputs.items()}, "reviewer_inputs": False}
    (out / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify(out)
    print(json.dumps({"prepared": str(out), "parent": metric["session_id"], "model_calls": 0}))


def verify(out):
    m = SKILL.verify(out)
    PAIRED.verify(Path(m["completion"]["review_root"]))
    for path, digest in m["completion"]["files"].items():
        if BASE.sha(path) != digest:
            raise ValueError("Frozen completion input changed: " + path)
    return m


def audit(out):
    m, run_dir = verify(out), out / "runs/inquiry/rep1"
    metric = BASE.read(run_dir / "metrics.json")
    child = PAIRED.rows(run_dir / "transcript.jsonl")
    parent = PAIRED.rows(out / "parent-native.jsonl")
    binding = AUDITOR.history_binding(parent, child, m["completion"]["parent_session"], m["completion"]["parent_bytes"])
    confirmed = binding["native_history_binding_confirmed"]
    delivery, skill = BASE.read(run_dir / "delivery-audit.json"), BASE.read(run_dir / "skill-delivery.json")
    result = {"model_calls": 0, "semantic_verified": False, "parent_session": m["completion"]["parent_session"],
        "parent_sha256": m["completion"]["parent_sha256"], "child_session": metric["session_id"],
        **binding,
        "identity_confirmed": metric["status"] == "completed" and metric["actual_models"] == [RAW.MODEL]
            and metric["actual_effort"] == "high" and metric["recording_complete"] and metric["report_present"]
            and child[0]["payload"].get("id", child[0]["payload"].get("session_id")) == metric["session_id"],
        "full_instruction_delivery": skill["full_instruction_delivery"], "delivery_errors": delivery["errors"],
        "report_id": delivery["report_id"], "host_skill_catalog_absent": metric["host_skill_catalog_absent"],
        "limit": m["comparison_limit"] + " Native history binding does not prove model attention."}
    if confirmed:
        result["usage"] = PAIRED.review_usage(parent, child, (out / "prompt.md").read_text(encoding="utf-8"))
    BASE.save(run_dir / "completion-audit.json", result)
    if not (confirmed and result["identity_confirmed"] and result["full_instruction_delivery"] and not delivery["errors"]):
        raise ValueError("Completion audit failed; preserve artifacts, no retry")
    print(json.dumps(result, ensure_ascii=False))


def run(out):
    m = verify(out)
    if (out / "runs/inquiry/rep1").exists():
        raise FileExistsError("Completion already started; no replacement run")
    command = RAW.command
    try:
        with patch.object(RAW, "command", lambda pool, config: PAIRED.fork_command(command(pool, config), m["completion"]["parent_session"])):
            SKILL.run(out)
    finally:
        verify(out)
    audit(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "verify", "audit"))
    parser.add_argument("--review-root", type=Path)
    parser.add_argument("--case")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        if not args.review_root or not args.case:
            parser.error("prepare requires --review-root and --case")
        prepare(args.out.resolve(), args.review_root.resolve(), args.case)
    else:
        globals()[args.mode](args.out.resolve())
