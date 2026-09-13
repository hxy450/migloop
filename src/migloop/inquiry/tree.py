"""One event-backed neighborhood for manual exploration and report paths.

Nodes are cumulative evidence scopes, not reconstructed filesystem snapshots.
Model-reviewed links live in a report overlay; they never enter effects.
"""

from __future__ import annotations

from collections import deque
import json

from .store import digest, encode, iso, parts, timestamp

_HISTORY = {
    op: "原始" + name + "关系；不认证问题内容传播。"
    for op, name in (("read", "读取"), ("write", "写入"), ("dispatch", "派发"))
}


def coordinate(kind, key, at, since=None):
    return {"kind": kind, "key": key, "at": iso(at), "since": iso(since)}


def indexed_event(row):
    op = row.get("op", "dispatch")
    if op == "dispatch":
        origin, destination = ("agent", row["parent"]), ("agent", row["child"])
    elif op in ("read", "write") and row["agent"]:
        agent, file = ("agent", row["agent"]), ("file", row["path"])
        origin, destination = (file, agent) if op == "read" else (agent, file)
    else:
        return None
    event = {
        "id": "native:" + row["id"],
        "relation": op,
        "at": row["at"],
        "from": origin,
        "to": destination,
        "source": "indexed",
        "strength": row.get("strength", "confirmed"),
        "evidence": [row[k] for k in ("request", "result") if row.get(k)],
        "claim": _HISTORY[op],
    }
    if op == "dispatch":
        event.update({key: row[key] for key in ("request", "result", "confirmed_at")})
    return event


def neighbor_row(event, scope, direction="upstream"):
    """Shared projection. Changing the view cutoff cannot change an event ID."""
    at = timestamp(scope["at"], required=True)
    since = timestamp(scope.get("since"))
    near, far = ("to", "from") if direction == "upstream" else ("from", "to")
    if tuple(event[near]) != (scope["kind"], scope["key"]):
        return None
    when = event["at"]
    if when is not None and (when > at or since is not None and when < since):
        return None
    timing = {}
    if event["relation"] == "dispatch":
        from .engine import project_dispatch

        event = project_dispatch(event, at)
        event["evidence"] = [event[k] for k in ("request", "result") if event.get(k)]
        timing = {
            "occurrence_at": iso(when),
            "confirmed_at": iso(event["confirmed_at"]),
            **{
                key: event[key]
                for key in ("identity_known_at_cutoff", "identity_basis", "status")
            },
        }
    kind, key = event[far]
    return {
        **{
            k: event[k]
            for k in ("id", "relation", "source", "strength", "evidence", "claim")
        },
        "at": iso(when),
        # This is a new upstream/downstream entity's full history, not the
        # original node's restricted window. Its original scope is unchanged.
        "node": coordinate(kind, key, when if when is not None else at),
        "time_unknown": when is None,
        **timing,
    }


def reviewed_edge(engine, edge, origin, destination, fid):
    """Validate locatable quotes, not the model's interpretation of those quotes."""
    from .engine import bounds, in_scope

    if "link" in edge:
        raise ValueError("reviewed relation uses raw evidence, not an indexed link")
    relation = {"possible_read": "read", "possible_write": "write"}.get(
        edge["relation"], edge["relation"]
    )
    expected = ("file", "agent") if relation == "read" else ("agent", "file")
    if (
        relation not in ("read", "write")
        or (origin["kind"], destination["kind"]) != expected
    ):
        raise ValueError("reviewed read/write has invalid endpoint direction")
    if not origin["exists"] or not destination["exists"]:
        raise ValueError("reviewed relation requires both recorded entities")
    review = edge["review"]
    if not isinstance(review, dict) or set(review) != {"at", "quotes"}:
        raise ValueError("review requires at and original quotes")
    when = timestamp(review["at"], required=True)
    if any(not in_scope(when, *bounds(n)) for n in (origin, destination)):
        raise ValueError("reviewed operation falls outside its endpoint scopes")
    quotes = review["quotes"]
    if not isinstance(quotes, list) or not 1 <= len(quotes) <= 8:
        raise ValueError("review requires 1–8 original quotes")
    records = {engine.store.source_record(ref)[0]["ref"] for ref in edge["evidence"]}
    matched_time = False
    for quote in quotes:
        if (
            not isinstance(quote, dict)
            or set(quote) != {"ref", "text"}
            or not isinstance(quote["text"], str)
            or not 1 <= len(quote["text"]) <= 10000
        ):
            raise ValueError(
                "each review quote requires ref and 1–10000 characters of text"
            )
        record, raw = engine.store.source_record(quote["ref"])
        if record["ref"] not in records:
            raise ValueError("review quote is not in this edge's evidence")
        opened = engine.query(
            {
                "op": "open",
                "ref": quote["ref"],
                "at": iso(
                    min(
                        timestamp(origin["at"], required=True),
                        timestamp(destination["at"], required=True),
                    )
                ),
            }
        )
        if quote["text"] not in opened["text"]:
            raise ValueError(
                "review quote does not occur in the cited original content"
            )
        # A real quote cannot reassign an already indexed native operation.
        # A mixed record can also contain an opaque script; without a unique
        # call anchor its adjacent native block is not contradictory evidence.
        if record["at"] == when:
            native = engine.store.rows(
                "SELECT op,agent,path FROM effects WHERE request=? OR result=?",
                (record["ref"], record["ref"]),
            )
            actor, file = (destination, origin) if relation == "read" else (origin, destination)
            if native and len(list(parts(json.loads(raw)))) == 1 and not any(
                e["op"] == relation and e["agent"] == actor["key"]
                and e["path"] == engine.store.resolve_file(file["key"])
                for e in native
            ):
                raise ValueError("reviewed relation contradicts indexed operation endpoints")
        matched_time |= record["at"] == when
    if not matched_time:
        raise ValueError("review time must identify a quoted original event")
    identity = digest(
        encode(
            {
                "from": [origin["kind"], origin["key"]],
                "to": [destination["kind"], destination["key"]],
                "relation": relation,
                "review": review,
                "evidence": sorted(records),
            }
        ).encode()
    )[:20]
    return {
        **edge,
        "from": origin["id"],
        "to": destination["id"],
        "finding": fid,
        "source": "model_review",
        "strength": "candidate",
        "operation": "review:" + identity,
        "at": iso(when),
        "semantic_verified": False,
        "quote_verified": True,
    }


def graph_events(graph, finding=None):
    nodes = {n["id"]: n for n in graph["nodes"]}
    events = []
    for edge in graph["edges"]:
        if finding is not None and edge["finding"] != finding:
            continue
        origin, destination = nodes[edge["from"]], nodes[edge["to"]]
        model = edge.get("source") == "model_review"
        relation = {"possible_read": "read", "possible_write": "write"}.get(
            edge["relation"], edge["relation"]
        )
        event = {
            "id": ("model:" if model else "native:") + edge["operation"],
            "relation": relation,
            "at": timestamp(edge.get("at")),
            "from": (origin["kind"], origin["key"]),
            "to": (destination["kind"], destination["key"]),
            "source": "model_review" if model else "indexed",
            "strength": edge["strength"],
            "evidence": edge["evidence"],
            "claim": edge["claim"] if model else _HISTORY[relation],
            "finding": edge["finding"],
        }
        if relation == "dispatch":
            if not {"request", "result", "confirmed_at"} <= edge.keys():
                continue  # An older cached graph needs load_report(recheck=True).
            event.update(
                request=edge["request"],
                result=edge["result"],
                confirmed_at=timestamp(edge["confirmed_at"]),
            )
        events.append(event)
    return events


def tree_neighbors(engine, scope, request):
    from .report import load_report

    direction = request.get("direction", "upstream")
    if direction not in ("upstream", "downstream"):
        raise ValueError("direction must be upstream or downstream")
    at, since = timestamp(scope["at"], required=True), timestamp(scope.get("since"))
    events = [
        indexed_event(row)
        for row in engine.relations(
            scope["kind"], scope["key"], at, since, request.get("undated", False)
        )
    ]
    if scope["kind"] == "agent":
        events.extend(
            indexed_event(row)
            for row in engine.dispatches(at, since, agent=scope["key"])
        )
    rejected_reviews = []
    if request.get("report_id"):
        # The saved overlay was checked at submission. Verify selected source
        # bytes below; do not rebuild every report/review on each mouse click.
        graph = load_report(engine, request["report_id"], recheck=False)
        if request.get("finding") and request["finding"] not in {
            f["id"] for f in graph["document"]["findings"]
        }:
            raise ValueError("unknown report finding")
        nodes = {n["id"]: n for n in graph["nodes"]}
        for edge in graph["edges"]:
            if edge.get("source") != "model_review" or (
                request.get("finding") and edge["finding"] != request["finding"]
            ):
                continue
            near = nodes[edge["to" if direction == "upstream" else "from"]]
            if (near["kind"], near["key"]) != (scope["kind"], scope["key"]):
                continue
            when = timestamp(edge.get("at"))
            if when is not None and (when > at or since is not None and when < since):
                continue
            try:
                # Cached overlays must obey the same current rules as submit;
                # recheck only incident supplemental edges, not the full report.
                checked = reviewed_edge(engine, edge, nodes[edge["from"]], nodes[edge["to"]], edge["finding"])
            except (ValueError, OSError) as exc:
                rejected_reviews.append({"finding": edge["finding"], "error": str(exc)})
                continue
            events.extend(graph_events({**graph, "edges": [checked]}))
    elif request.get("finding"):
        raise ValueError("finding requires a report_id")
    rows = {}
    for event in events:
        if event is None:
            continue
        row = neighbor_row(event, scope, direction)
        if row is not None:
            rows[row["id"]] = row
    ordered = sorted(
        rows.values(), key=lambda r: (r["at"] is None, r["at"] or "", r["id"])
    )
    page = engine._page(ordered, request.get("offset", 0), request.get("limit", 20))
    for row in page["rows"]:
        for ref in row["evidence"]:
            engine.store.source_record(ref)
    return {
        "kind": "neighbors",
        "scope": scope,
        "scope_id": engine.store.handle("s", scope),
        "direction": direction,
        **page,
        "rejected_reviews": rejected_reviews,
        "note": "历史范围的邻居，不是完整文件状态。模型复核边仅属于所载报告，虚线不认证语义。",
    }


def evidence_paths(engine, graph):
    """Time-monotone paths in cited evidence only, never a global shortest guess."""
    from .engine import in_scope

    target = graph["target"]
    root = coordinate(
        "file",
        engine.store.resolve_file(target["file"]),
        timestamp(target["at"], required=True),
    )
    paths, context_paths = [], []
    for finding in graph["document"]["findings"]:
        fid = finding["id"]
        events = graph_events(graph, fid)
        # Canonical evidence references are also needed when a report used handles.
        for event in events:
            event["refs"] = {
                engine.store.source_record(ref)[0]["ref"] for ref in event["evidence"]
            }
        incoming = {}
        for event in events:
            if event["at"] is not None:
                incoming.setdefault(tuple(event["to"]), []).append(event)
        for values in incoming.values():
            values.sort(key=lambda e: (e["strength"] != "confirmed", -e["at"], e["id"]))
        # A model may cite a returned input on its agent judgment instead of
        # naming a separate file node. attach() already supplies that neutral
        # endpoint; allow its cited read/dispatch arm, not every generated node.
        input_refs = {}
        for event in events:
            if event["relation"] in ("read", "dispatch"):
                input_refs.setdefault(tuple(event["from"]), set()).update(event["refs"])
        goals = [
            n
            for n in graph["nodes"]
            if n["finding"] == fid
            and n["role"] in ("origin", "propagated", "context", "repaired")
            and (
                not n["generated_context"]
                or bool(
                    input_refs.get((n["kind"], n["key"]), set()).intersection(
                        n["valid_refs"]
                    )
                )
            )
        ]
        change_refs = set()
        target_at = timestamp(target["at"], required=True)
        target_since = timestamp(target.get("since"))
        for ref in finding.get("changes", []):
            try:
                record, _ = engine.store.source_record(ref)
                if in_scope(record["at"], target_at, target_since):
                    change_refs.add(record["ref"])
            except (ValueError, OSError):
                continue
        repairs = []
        for operation in engine.relations("file", root["key"], target_at, target_since):
            if operation["op"] == "write" and change_refs.intersection(
                {operation["request"], operation["result"]}
            ):
                event = indexed_event(operation)
                if event is not None and event["at"] is not None:
                    try:
                        for ref in event["evidence"]:
                            engine.store.source_record(ref)
                    except (ValueError, OSError):
                        continue  # A stale receipt cannot confirm the repair anchor.
                    repairs.append(event)
        repairs.extend(
            event
            for event in events
            if event["source"] == "model_review"
            and event["relation"] == "write"
            and tuple(event["to"]) == ("file", root["key"])
            and in_scope(event["at"], target_at, target_since)
            and change_refs.intersection(event["refs"])
        )
        repair = max(
            repairs,
            key=lambda e: (e["at"], e["strength"] == "confirmed", e["id"]),
            default=None,
        )
        repair_at = repair["at"] if repair else None
        repair_row = neighbor_row(repair, root) if repair else None
        for goal in goals:
            queue = deque([(root, [], frozenset(), frozenset())])
            found = None
            anchor = None
            inspected = 0
            while queue and inspected < 10000 and repair_at is not None:
                scope, steps, seen, incident = queue.popleft()
                inspected += 1
                current = (scope["kind"], scope["key"])
                at = timestamp(scope["at"], required=True)
                goal_since = timestamp(goal.get("since"))
                # A context judgment on an agent can cite its received input,
                # not its output write. Certify that actual incoming operation
                # within the reached window, without reclassifying the input.
                received_context = (
                    goal["role"] == "context"
                    and goal["kind"] == "agent"
                    and any(
                        event["relation"] in ("read", "dispatch")
                        and event["strength"] == "confirmed"
                        and in_scope(event["at"], at, goal_since)
                        and event["refs"].intersection(goal["valid_refs"])
                        for event in incoming.get(current, [])
                    )
                )
                hit = (
                    current == (goal["kind"], goal["key"])
                    and at <= timestamp(goal["at"], required=True)
                    and (goal_since is None or at >= goal_since)
                    and (bool(incident.intersection(goal["valid_refs"])) or received_context)
                )
                # A target-file claim is already at the root, but still needs an
                # actual cited incoming write corresponding to its history.
                if hit:
                    found = steps
                    break
                for event in incoming.get(current, []):
                    if event["id"] in seen or event["at"] > min(at, repair_at):
                        continue
                    row = neighbor_row(event, scope)
                    if row is None:
                        continue
                    if (
                        not steps
                        and current == (goal["kind"], goal["key"])
                        and event["refs"].intersection(goal["valid_refs"])
                        and (goal_since is None or event["at"] >= goal_since)
                        and event["at"] <= timestamp(goal["at"], required=True)
                    ):
                        found = []
                        anchor = row
                        break
                    visible_refs = frozenset(
                        engine.store.source_record(ref)[0]["ref"]
                        for ref in row["evidence"]
                    )
                    queue.append(
                        (row["node"], steps + [row], seen | {event["id"]}, visible_refs)
                    )
                if found is not None:
                    break
            support = (
                (found or [])
                + ([anchor] if anchor else [])
                + ([repair_row] if repair_row else [])
            )
            status = (
                "unclosed"
                if found is None
                else "model_review"
                if any(s["source"] == "model_review" for s in support)
                else "candidate"
                if any(s["strength"] != "confirmed" for s in support)
                else "native"
            )
            # Normal inputs need the same temporal/source checks as problem
            # nodes, but their display coverage is not causal-path completion.
            # Fixes/new contracts still belong on the display tree without
            # inventing a generation-fault node to make their path visible.
            display_only = goal["role"] in ("context", "repaired")
            destination = context_paths if display_only else paths
            destination.append(
                {
                    "finding": fid,
                    "node": goal["id"],
                    "purpose": "context" if display_only else "problem",
                    "status": status,
                    "steps": found or [],
                    "anchor": anchor,
                    "repair_anchor": repair_row,
                    "diagnostic": (
                        "缺少目标修改引用或到此节点的同问题、非倒序证据路径。"
                        + (
                            " 路径搜索达到预算，未证明不存在。"
                            if inspected >= 10000
                            else ""
                        )
                    )
                    if found is None
                    else "历史关系路径已接通；内容传播和原因仍是模型主张。",
                }
            )
    return {
        "root": root,
        "paths": paths,
        "context_paths": context_paths,
        "complete": all(p["status"] != "unclosed" for p in paths),
        "problem_nodes": len(paths),
        "note": "自动展开与手动展开共用邻居投影；不是模型实际查询顺序，也不认证文件状态连续。",
    }
