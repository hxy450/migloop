"""Prepare issue jobs and enrich semantic drafts without altering their claims."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from datetime import datetime

from .common import fields, fingerprint, load, nonempty, now, strings, write_new
from . import VERSION
from .provenance import collect, verify_materials, _bundle_hash
from .registry import revision_of


def dispatch(tasks_path, metadata_path, out):
    tasks, metadata, out = load(tasks_path), load(metadata_path), Path(out).resolve()
    if tasks.get("schema") != "migloop-repair-triage/1" or metadata.get("schema") != "migloop-provenance/1":
        raise ValueError("Expected repair-triage/1 tasks and collected provenance/1 metadata")
    if out.exists():
        raise ValueError("Dispatch output must be a new directory; previous jobs are not overwritten")
    issues = tasks.get("issues")
    if not isinstance(issues, list) or not isinstance(tasks.get("scope"), dict):
        raise ValueError("Task scope and issue list required")
    materials = tasks["scope"].get("materials", [])
    if not isinstance(materials, list) or str(Path(metadata["materials"]).resolve()) not in {
            str(Path(p).resolve()) for p in materials if isinstance(p, str)}:
        raise ValueError("Task materials do not match the collected provenance pool; do not bind unrelated sessions")
    declared = metadata.get("migration", {})
    # Identity is not a hash of mutable evidence. Server IDs survive cloud imports;
    # local inputs use the stable scope location and explicitly retain that limit.
    migration_key = declared.get("id") or declared.get("server_session_id")
    identity_basis = "server migration ID"
    if not migration_key:
        migration_key = str(Path(metadata["materials"]).resolve())
        identity_basis = "local material location; preserve job ID across relocation/retitling"
        if metadata.get("db_root_session_id"):
            migration_key += "#session=" + metadata["db_root_session_id"]
            identity_basis = "local DB location + explicit root session; preserve job ID across relocation/retitling"
    prepared, titles = [], set()
    for number, issue in enumerate(issues, 1):
        nonempty(issue.get("title"), f"issue {number}.title")
        if issue["title"] in titles:
            raise ValueError("Issue titles must distinguish tasks within a migration; duplicate title is ambiguous")
        titles.add(issue["title"])
        if not isinstance(issue.get("changes"), list) or not issue["changes"]:
            raise ValueError(f"issue {number}: changes required")
        targets = sorted({p for change in issue["changes"]
                          for p in strings(change.get("files"), "changes.files", empty=False)})
        job_id = "issue-" + fingerprint([migration_key, issue["title"]])[:20]
        job = {"schema": "migloop-issue-job/1", "id": job_id, "scope": tasks["scope"],
               "issue": issue, "targets": targets, "pending": tasks.get("pending", []),
               "provenance_path": "../../provenance.json", "provenance_sha256": fingerprint(metadata),
               "identity_basis": identity_basis, "migration_key": migration_key}
        prepared.append((job_id, job))
    out.mkdir(parents=True)
    write_new(out / "provenance.json", metadata)
    jobs = []
    for job_id, job in prepared:
        path = out / "jobs" / job_id / "job.json"
        write_new(path, job)
        # A short prompt; task detail lives in the frozen job, not a rich answer-bearing prompt.
        prompt = "使用 $migloop-build-cards 的单问题制卡流程。\n任务：" + str(path) + "\n"
        path.with_name("prompt.txt").write_text(prompt, encoding="utf-8")
        jobs.append({"id": job_id, "title": job["issue"]["title"], "job": str(path), "targets": job["targets"]})
    manifest = {"schema": "migloop-card-jobs/1", "jobs": jobs,
                "set_aside": tasks.get("set_aside", []), "pending": tasks.get("pending", []),
                "coverage": tasks.get("coverage", {}), "model_calls": 0}
    write_new(out / "jobs.json", manifest)
    return {"jobs": len(jobs), "manifest": str(out / "jobs.json"), "model_calls": 0}


def _absolute(path, scope):
    path = path.replace("\\", "/")
    if path.startswith("/") or len(path) > 2 and path[1] == ":":
        return path
    roots = scope.get("project_roots", [])
    if len(roots) != 1:
        raise ValueError("Relative target needs exactly one historical project root")
    return str(PurePosixPath(roots[0].replace("\\", "/")) / path)


def _graph_shape(graph):
    fields(graph, ("target", "summary", "recommendations", "nodes", "edges"),
           ("target", "summary", "recommendations", "nodes", "edges"), "graph")
    fields(graph["target"], ("key", "since", "at"), ("key", "at"), "graph.target")
    def time(value):
        if not isinstance(value, str):
            raise ValueError("Graph timestamps must be timezone-aware ISO strings, not unknown/null")
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid historical ISO timestamp: " + value) from exc
        if result.tzinfo is None:
            raise ValueError("Historical timestamps must include a timezone")
        return result
    end = time(graph["target"]["at"])
    if "since" in graph["target"] and time(graph["target"]["since"]) > end:
        raise ValueError("Graph target since is later than at")
    nonempty(graph["target"]["key"], "graph.target.key")
    nonempty(graph["summary"], "graph.summary")
    strings(graph["recommendations"], "graph.recommendations")
    if not isinstance(graph["nodes"], list) or not graph["nodes"] or not isinstance(graph["edges"], list):
        raise ValueError("graph.nodes and graph.edges must be lists; declare real nodes")
    for node in graph["nodes"]:
        fields(node, ("key", "at", "reason", "problem"), ("key", "at", "reason"), "graph.node")
        for key in ("key", "at", "reason"):
            nonempty(node[key], "graph.node." + key)
        if time(node["at"]) > end:
            raise ValueError("Node timestamp exceeds observation end")
        if type(node.get("problem", False)) is not bool:
            raise ValueError("problem must be boolean")
    # Full temporal/effect validation belongs to the unchanged inquiry checker.
    for edge in graph["edges"]:
        fields(edge, ("from", "to", "force", "reason", "evidence"), ("from", "to"), "graph.edge")
        for endpoint in (edge["from"], edge["to"]):
            if endpoint != "target" and (type(endpoint) is not int or not 1 <= endpoint <= len(graph["nodes"])):
                raise ValueError("Edge endpoint must be a declared 1-based node number or target")


def pack(job_path, draft_path, out, db=None):
    job_path, out = Path(job_path).resolve(), Path(out).resolve()
    job, draft = load(job_path), load(draft_path)
    if job.get("schema") != "migloop-issue-job/1":
        raise ValueError("Expected a dispatch-created issue job")
    metadata = load(job_path.parent / job["provenance_path"])
    if fingerprint(metadata) != job["provenance_sha256"]:
        raise ValueError("Frozen job provenance changed; recollect and create a new job")
    verify_materials(metadata)
    fields(draft, ("title", "when", "summary", "recommendations", "unknown", "graphs", "unresolved_targets"),
           ("title", "when", "summary", "recommendations", "unknown", "graphs"), "draft")
    for key in ("title", "when", "summary"):
        nonempty(draft[key], "draft." + key)
    strings(draft["recommendations"], "draft.recommendations")
    strings(draft["unknown"], "draft.unknown")
    if not isinstance(draft["graphs"], list):
        raise ValueError("graphs must be a list")
    expected = {_absolute(p, job["scope"]) for p in job["targets"]}
    covered, unresolved = set(), set()
    for graph in draft["graphs"]:
        _graph_shape(graph)
        target = _absolute(graph["target"]["key"], job["scope"])
        if target not in expected or target in covered:
            raise ValueError("Graph targets must be distinct members of this issue, not another issue's files")
        for field, scope_field in (("since", "generation_end"), ("at", "observation_end")):
            if graph["target"].get(field) != job["scope"].get(scope_field):
                raise ValueError(f"graph.target.{field} must preserve the dispatched task window")
        covered.add(target)
    for item in draft.get("unresolved_targets", []):
        fields(item, ("key", "reason"), ("key", "reason"), "unresolved target")
        nonempty(item["reason"], "unresolved target reason")
        target = _absolute(item["key"], job["scope"])
        if target not in expected or target in covered or target in unresolved:
            raise ValueError("Unresolved targets must be distinct issue targets without a graph")
        unresolved.add(target)
    if expected != covered | unresolved:
        raise ValueError("Targets without a graph or explicit unresolved reason: " + ", ".join(sorted(expected - covered - unresolved)))
    if out.exists():
        raise ValueError("Card output exists; use a new revision filename")
    views = out.parent / (out.stem + ".views")
    if views.exists():
        raise ValueError("View output exists; choose another output basename")
    if not db and any(edge.get("force") for graph in draft["graphs"] for edge in graph["edges"]):
        raise ValueError("force requires the existing inquiry checker and its previous feedback; no --db supplied")
    checks = []
    if db and draft["graphs"]:
        if not Path(db).is_file():
            raise ValueError("Inquiry DB does not exist; import the provided pool first")
        try:
            from migloop.inquiry.engine import Engine
            from migloop.inquiry.report import check
            from migloop.inquiry.store import Store
        except ImportError as exc:
            raise ValueError("Optional graph check needs installed migloop[inquiry]; core/UI are not bundled here") from exc
        store = Store(str(db))
        try:
            engine = Engine(store, session="memory-card:" + job["id"], origin="memory-skill")
            for index, graph in enumerate(draft["graphs"]):
                try:
                    receipt = check(engine, json.dumps(graph, ensure_ascii=False), save=True)
                except (ValueError, TypeError) as exc:
                    receipt = {"status": "rejected", "error": str(exc)}
                checks.append({"graph": index + 1, "draft_sha256": fingerprint(graph), "receipt": receipt})
        finally:
            store.close()
    claims = {"diagnosis": {"text": draft["summary"], "kind": "diagnosis", "status": "model_claim"}}
    for index, recommendation in enumerate(draft["recommendations"], 1):
        claims[f"recommendation:{index}"] = {"text": recommendation, "kind": "recommendation", "status": "model_claim"}
    sources = {s["source"]: s for s in metadata["sources"]}
    mentioned = {n["key"] for g in draft["graphs"] for n in g["nodes"]}
    matched = {key: value for key, value in sources.items() if key in mentioned}
    card = {"schema": "migloop-case/1", "id": "case-" + job["id"].removeprefix("issue-"),
            "created_at": now(), "job": job["id"], "identity_basis": job.get("identity_basis"),
            "migration_key": job.get("migration_key"), "draft": draft, "claims": claims,
            "targets": sorted(expected), "changes": job["issue"]["changes"],
            "participants": job["issue"].get("participants", []), "scope": job["scope"],
            "provenance": metadata, "node_provenance": matched,
            "packager": {"name": "migloop-memory-skills", "version": VERSION, "bundle_sha256": _bundle_hash()},
            "validation": {"schema": "passed", "graph_checks": checks,
                           "graph_check": "performed" if checks else "not_run",
                           "causal_correctness": "not_certified", "unresolved_targets": sorted(unresolved)}}
    # Timestamp does not manufacture a new semantic revision on an identical repack.
    card["revision"] = revision_of(card)
    write_new(out, card)
    for index, graph in enumerate(draft["graphs"], 1):
        write_new(views / f"target-{index}.json", graph)
    return {"card": str(out), "id": card["id"], "revision": card["revision"],
            "graphs": len(draft["graphs"]), "views": str(views) if draft["graphs"] else None, "validation": card["validation"]}


def main(role):
    if role not in ("triage", "card"):
        raise ValueError("Unknown skill role: " + str(role))
    parser = argparse.ArgumentParser(description="Prepare issue jobs." if role == "triage" else "Package one issue card.")
    commands = parser.add_subparsers(dest="command", required=True)
    if role == "triage":
        metadata = commands.add_parser("metadata")
        metadata.add_argument("--pool", required=True)
        metadata.add_argument("--server-metadata")
        metadata.add_argument("--session-id")
        metadata.add_argument("--out", required=True)
        jobs = commands.add_parser("dispatch")
        jobs.add_argument("--tasks", required=True)
        jobs.add_argument("--metadata", required=True)
        jobs.add_argument("--out", required=True)
    else:
        packing = commands.add_parser("pack")
        packing.add_argument("--job", required=True)
        packing.add_argument("--draft", required=True)
        packing.add_argument("--out", required=True)
        packing.add_argument("--db")
    args = parser.parse_args()
    if args.command == "metadata":
        result = collect(args.pool, args.server_metadata, args.session_id)
        write_new(args.out, result)
        result = {"metadata": args.out, "sources": len(result["sources"]), "observed": result["observed"], "unknown": result["unknown"]}
    elif args.command == "dispatch":
        result = dispatch(args.tasks, args.metadata, args.out)
    else:
        result = pack(args.job, args.draft, args.out, args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
