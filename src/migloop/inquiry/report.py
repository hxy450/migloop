"""Bind a model's argument without rewriting its reasons or inventing graph edges."""

from __future__ import annotations

import json
import re
import uuid

from .coverage import reconcile
from .engine import bounds, in_scope
from .evidence_graph import attach
from .store import digest, encode, iso, timestamp


def parse(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 80000:
        raise ValueError("report must be 1–80000 characters")
    try:
        result = json.loads(text)
    except ValueError:
        import yaml

        try:
            if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
                raise ValueError("YAML aliases are not allowed")
            result = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError("invalid YAML") from exc
    if not isinstance(result, dict) or result.get("schema") != "inquiry/1":
        raise ValueError("schema must be inquiry/1")
    if set(result) - {"schema", "target", "findings", "unexplained", "reviewed"}:
        raise ValueError("unknown report fields")
    if not isinstance(result.get("reviewed", []), list):
        raise TypeError("reviewed must be a list")
    findings = result.get("findings")
    if not isinstance(findings, list) or len(findings) > 100:
        raise ValueError("findings must be a list of at most 100 items")
    target = result.get("target")
    if not isinstance(target, dict):
        raise TypeError("target.file required")
    if "scope" in target:
        if set(target) != {"scope"}:
            raise ValueError("target uses scope or file/time, not both")
    else:
        if not isinstance(target.get("file"), str):
            raise TypeError("target.file required")
        bounds(target)
    return result


def check(engine, text, *, save=False):
    document = parse(text)
    target = document["target"]
    if "scope" in target:
        coordinate = engine.store.handle_value(target["scope"], "s")
        if coordinate["kind"] != "file":
            raise ValueError("target scope must be a file")
        target = {
            "file": coordinate["key"],
            "at": coordinate["at"],
            "since": coordinate.get("since"),
        }
    nodes, edges, unverified, issues = [], [], [], []
    referenced = set()
    explained_changes = set()

    def verify_refs(refs, at, where, since=None):
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            issues.append(
                {"where": where, "error": "evidence must be a list of original refs"}
            )
            return set()
        valid = set()
        for ref in refs:
            try:
                record, _ = engine.store.source_record(ref)
                if not in_scope(record["at"], at, since):
                    raise ValueError("evidence outside node time range or undated")
                valid.add(record["ref"])
                referenced.add(record["ref"])
            except (ValueError, OSError) as exc:
                issues.append({"where": where, "ref": ref, "error": str(exc)})
        return valid

    def verify_text(value, at, where, since=None):
        if isinstance(value, str):
            verify_refs(re.findall(r"\be-[0-9a-f]{8,64}\b", value), at, where, since)
        elif isinstance(value, list):
            for item in value:
                verify_text(item, at, where, since)

    seen_findings = set()
    for index, finding in enumerate(document["findings"]):
        if not isinstance(finding, dict) or set(finding) - {
            "id",
            "title",
            "reason",
            "changes",
            "nodes",
            "edges",
            "unknown",
            "hypothesis",
            "recommendation",
        }:
            raise ValueError("invalid finding fields")
        fid = finding.get("id")
        if not isinstance(fid, str) or not fid or fid in seen_findings:
            raise ValueError("finding IDs must be nonempty and unique")
        seen_findings.add(fid)
        if not isinstance(finding.get("nodes", []), list) or any(
            not isinstance(n, dict) for n in finding.get("nodes", [])
        ):
            raise TypeError("nodes must be a list of objects")
        original_node_ids = {
            n.get("id") for n in finding.get("nodes", []) if isinstance(n, dict)
        }
        automatic_edges = "edges" not in finding
        finding = attach(engine, finding, target)
        for field in ("title", "reason", "unknown", "hypothesis", "recommendation"):
            verify_text(
                finding.get(field),
                timestamp(target["at"], required=True),
                f"{fid}.{field}",
            )
        if any(
            not isinstance(finding.get(k), str) or not finding[k].strip()
            for k in ("title", "reason")
        ):
            raise ValueError("finding title and reason required")
        explained_changes.update(
            verify_refs(
                finding.get("changes", []),
                timestamp(target["at"], required=True),
                f"{fid}.changes",
                timestamp(target.get("since")),
            )
        )
        local = {}
        if not isinstance(finding.get("nodes", []), list) or not isinstance(
            finding.get("edges", []), list
        ):
            raise TypeError("nodes and edges must be lists")
        for node in finding.get("nodes", []):
            if not isinstance(node, dict) or set(node) - {
                "id",
                "kind",
                "key",
                "at",
                "since",
                "role",
                "reason",
                "evidence",
                "scope",
            }:
                raise ValueError("invalid node fields")
            nid = node.get("id")
            if not isinstance(nid, str) or not nid or nid in local:
                raise ValueError("node IDs must be unique within a finding")
            if "scope" in node:
                if any(k in node for k in ("kind", "key", "at", "since")):
                    raise ValueError(
                        "node uses scope or explicit coordinates, not both"
                    )
                coordinate = engine.store.handle_value(node["scope"], "s")
                node = {
                    **node,
                    **{k: coordinate[k] for k in ("kind", "key", "at")},
                    "since": coordinate.get("since"),
                }
            if node.get("kind") not in ("file", "agent") or not isinstance(
                node.get("key"), str
            ):
                raise ValueError("node kind/file-or-agent key required")
            if node.get("role") not in (
                "origin",
                "propagated",
                "context",
                "repaired",
                "unknown",
            ):
                raise ValueError("invalid node role")
            if not isinstance(node.get("reason"), str) or not node["reason"].strip():
                raise ValueError("every node requires its original reason")
            at, since = bounds(node)
            key = (
                engine.store.resolve_file(node["key"])
                if node["kind"] == "file"
                else node["key"]
            )
            try:
                exists = engine.store.has_records(node["kind"], key, at, since=since)
            except ValueError:
                exists = False
            refs = verify_refs(node.get("evidence", []), at, f"{fid}.{nid}", since)
            verify_text(node["reason"], at, f"{fid}.{nid}.reason", since)
            if not exists:
                issues.append(
                    {
                        "where": f"{fid}.{nid}",
                        "error": "node has no recorded evidence at cutoff",
                    }
                )
            bound = {
                **node,
                "id": f"{fid}:{nid}",
                "key": key,
                "finding": fid,
                "exists": exists,
                "valid_refs": sorted(refs),
                "semantic_verified": False,
                "generated_context": nid not in original_node_ids,
            }
            local[nid] = bound
            nodes.append(bound)
        for edge in finding.get("edges", []):
            operation_id = None
            if not isinstance(edge, dict) or set(edge) - {
                "from",
                "to",
                "relation",
                "evidence",
                "claim",
                "link",
            }:
                raise ValueError("invalid edge fields")
            if "link" in edge:
                if "evidence" in edge or "relation" in edge:
                    raise ValueError(
                        "edge uses link or explicit evidence/relation, not both"
                    )
                coordinate = engine.store.handle_value(edge["link"], "l")
                operation_id = coordinate["operation"]
                edge = {**edge, **{k: coordinate[k] for k in ("relation", "evidence")}}
            if edge.get("relation") not in (
                "read",
                "write",
                "possible_read",
                "possible_write",
                "dispatch",
            ):
                raise ValueError("invalid relation kind")
            if not isinstance(edge.get("claim"), str) or not edge["claim"].strip():
                raise ValueError("edge claim required")
            origin, destination = local.get(edge.get("from")), local.get(edge.get("to"))
            reason = "node missing"
            bound = None
            if origin and destination:
                relation = edge.get("relation")
                op = {
                    "read": "read",
                    "write": "write",
                    "possible_read": "read",
                    "possible_write": "write",
                }.get(relation)
                file, agent = (
                    (origin, destination) if op == "read" else (destination, origin)
                )
                cutoff = min(
                    timestamp(origin["at"], required=True),
                    timestamp(destination["at"], required=True),
                )
                starts = [
                    timestamp(n["since"], required=True)
                    for n in (origin, destination)
                    if n.get("since") is not None
                ]
                start = max(starts) if starts else None
                refs = verify_refs(edge.get("evidence", []), cutoff, f"{fid}.edge")
                reason = "no matching indexed operation; independent lookup is not a read/write edge"
                if (
                    relation == "dispatch"
                    and origin["kind"] == destination["kind"] == "agent"
                ):
                    for dispatch in engine.store.rows(
                        "SELECT * FROM dispatches WHERE parent=? AND child=? AND at<=?",
                        (origin["key"], destination["key"], cutoff),
                    ):
                        if not in_scope(dispatch["at"], cutoff, start):
                            continue
                        if {dispatch["request"], dispatch["result"]} <= refs:
                            bound = {
                                **edge,
                                "from": origin["id"],
                                "to": destination["id"],
                                "finding": fid,
                                "strength": "confirmed",
                                "operation": dispatch["id"],
                                "semantic_verified": False,
                            }
                            break
                if (
                    op
                    and file["kind"] == "file"
                    and agent["kind"] == "agent"
                    and origin["exists"]
                    and destination["exists"]
                ):
                    matches = []
                    for operation in engine.relations("file", file["key"], cutoff):
                        expected = {operation["request"], operation["result"]} - {None}
                        if (
                            operation["agent"] == agent["key"]
                            and (
                                operation_id is None or operation["id"] == operation_id
                            )
                            and operation["op"] == op
                            and in_scope(operation["at"], cutoff, start)
                            and expected
                            and expected <= refs
                        ):
                            matches.append(
                                {
                                    **edge,
                                    "from": origin["id"],
                                    "to": destination["id"],
                                    "finding": fid,
                                    "strength": operation["strength"],
                                    "operation": operation["id"],
                                    "semantic_verified": False,
                                }
                            )
                    if len(matches) == 1:
                        bound = matches[0]
                    elif len(matches) > 1:
                        reason = "multiple operations share these record references; use the returned link to select its exact block"
            if bound:
                bound["source"] = "native_evidence" if automatic_edges else "model_edge"
                edges.append(bound)
            else:
                unverified.append({**edge, "finding": fid, "diagnostic": reason})
    verify_text(
        document.get("unexplained"),
        timestamp(target["at"], required=True),
        "unexplained",
    )
    missing_links = []
    paths = {n["key"] for n in nodes if n["kind"] == "file"} | {
        engine.store.resolve_file(target["file"])
    }
    connected = {edge["operation"] for edge in edges}
    cutoff = timestamp(target["at"], required=True)
    for path in sorted(paths):
        for operation in engine.relations("file", path, cutoff):
            if (
                operation["id"] in connected
                or operation["op"] not in ("read", "write")
                or not referenced.intersection(
                    {operation["request"], operation["result"]}
                )
                or not operation["agent"]
            ):
                continue
            # Suggest only already-cited native relationships, not new causal answers.
            missing_links.append(engine.link_view(operation, iso(cutoff)))
    coverage = reconcile(engine, target, document, explained_changes)
    result = {
        "schema": "inquiry-graph/1",
        "document": document,
        "target": target,
        "nodes": nodes,
        "edges": edges,
        "unverified_edges": unverified,
        "issues": issues,
        "semantic_verified": False,
        "mechanical_status": "needs_revision"
        if issues
        or unverified
        or missing_links
        or coverage["unattributed_native_writes"]
        or coverage["issues"]
        else "valid",
        "missing_evidence_links": missing_links,
        "coverage": coverage,
        "source_sha256": digest(text.encode()),
        "trace_session": engine.session,
        "note": "Reasons are model claims. Bound references/operations are not causal proof.",
    }
    if save:
        identity = uuid.uuid4().hex[:16]
        with engine.store.db:
            engine.store.db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?)",
                (identity, "report", text, encode(result), ""),
            )
        result["report_id"] = identity
    return result
