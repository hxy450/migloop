"""Bind a model's argument without rewriting its reasons or inventing graph edges."""

from __future__ import annotations

import json
import uuid

from .engine import bounds, in_scope
from .store import digest, encode, timestamp


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
    if set(result) - {"schema", "target", "findings", "unexplained"}:
        raise ValueError("unknown report fields")
    findings = result.get("findings")
    if not isinstance(findings, list) or len(findings) > 100:
        raise ValueError("findings must be a list of at most 100 items")
    target = result.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("file"), str):
        raise TypeError("target.file required")
    bounds(target)
    return result


def check(engine, text, *, save=False):
    document = parse(text)
    nodes, edges, unverified, issues = [], [], [], []

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
                    raise ValueError("evidence outside node cutoff or undated")
                valid.add(ref)
            except (ValueError, OSError) as exc:
                issues.append({"where": where, "ref": ref, "error": str(exc)})
        return valid

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
        if any(
            not isinstance(finding.get(k), str) or not finding[k].strip()
            for k in ("title", "reason")
        ):
            raise ValueError("finding title and reason required")
        verify_refs(
            finding.get("changes", []),
            timestamp(document["target"]["at"], required=True),
            f"{fid}.changes",
            timestamp(document["target"].get("since")),
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
                "role",
                "reason",
                "evidence",
            }:
                raise ValueError("invalid node fields")
            nid = node.get("id")
            if not isinstance(nid, str) or not nid or nid in local:
                raise ValueError("node IDs must be unique within a finding")
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
            at = timestamp(node.get("at"), required=True)
            key = (
                engine.store.resolve_file(node["key"])
                if node["kind"] == "file"
                else node["key"]
            )
            try:
                existence_query = {
                    "op": node["kind"],
                    "key": key,
                    "at": node["at"],
                    "limit": 1,
                }
                if node["kind"] == "file" and "/" in key:
                    # Basename hits are useful navigation, not proof of a claimed full path.
                    existence_query["terms"] = [key, key.replace("/", "\\")]
                exists = engine.query(existence_query)["total"] > 0
            except ValueError:
                exists = False
            refs = verify_refs(node.get("evidence", []), at, f"{fid}.{nid}")
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
            }
            local[nid] = bound
            nodes.append(bound)
        for edge in finding.get("edges", []):
            if not isinstance(edge, dict) or set(edge) - {
                "from",
                "to",
                "relation",
                "evidence",
                "claim",
            }:
                raise ValueError("invalid edge fields")
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
                    for operation in engine.relations("file", file["key"], cutoff):
                        expected = {operation["request"], operation["result"]} - {None}
                        if (
                            operation["agent"] == agent["key"]
                            and operation["op"] == op
                            and expected
                            and expected <= refs
                        ):
                            bound = {
                                **edge,
                                "from": origin["id"],
                                "to": destination["id"],
                                "finding": fid,
                                "strength": operation["strength"],
                                "operation": operation["id"],
                                "semantic_verified": False,
                            }
                            break
            if bound:
                edges.append(bound)
            else:
                unverified.append({**edge, "finding": fid, "diagnostic": reason})
    result = {
        "schema": "inquiry-graph/1",
        "document": document,
        "nodes": nodes,
        "edges": edges,
        "unverified_edges": unverified,
        "issues": issues,
        "semantic_verified": False,
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
