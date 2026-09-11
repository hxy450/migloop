"""Review cited evidence, not the truth of a model's causal explanation.

No prose classification, state replay, new edges, or model-authored corrections.
Literal predecessors are deliberately weaker than line authorship.
"""

from collections import defaultdict

from .citations import cited_refs
from .native_text import change_outline, change_payloads
from .store import iso, timestamp


def post_write_returns(engine, operations, target, limitations):
    """Literal markers in later same-actor returns, NOT target validation facts."""
    start = timestamp(target.get("since"))
    latest = {}
    for op in operations:
        if op["op"] == "write" and op["agent"] and (start is None or op["at"] >= start):
            latest[op["agent"]] = max(op["at"], latest.get(op["agent"], op["at"]))
    rows = []
    for agent, at in sorted(latest.items()):
        all_returns = {
            "op": "agent",
            "key": agent,
            "since": iso(at),
            "at": target["at"],
            "view": "returns",
            "offset": 0,
            "limit": 20,
        }
        query = {
            **all_returns,
            "limit": 5,
            "terms": [
                "BUILD SUCCESSFUL",
                "BUILD FAILED",
                "BUILD_EXIT_CODE",
                "install bundle successfully",
                "INSTALL_FAILED",
                "tests passed",
                "tests failed",
                "test result",
            ],
        }
        data = engine.query(query)
        matches = []
        for row in data["rows"]:
            try:
                engine.store.source_record(row["ref"])
            except (ValueError, OSError) as exc:
                limitations.append({"ref": row["cite"], "error": str(exc)})
                continue
            matches.append(
                {k: row[k] for k in ("cite", "at", "name", "line", "tools", "excerpt")}
            )
        rows.append(
            {
                "agent": agent,
                "since": iso(at),
                "at": target["at"],
                "total": data["total"],
                "matches": matches,
                "next": data["next"],
                "query": query,
                "all_returns_query": all_returns,
                "not_validation_proof": True,
                "not_absence_proof": True,
                "note": "Server lookup, not a model-opened source. Markers in recorded tool returns may be quoted docs, old logs or another target. Received after the last indexed target write does not prove the command started after it, built that state, or passed behavior tests. Open originals and paired commands; zero hits does not prove no validation.",
            }
        )
    return rows


def review(engine, document, target, nodes):
    store = engine.store
    cutoff = timestamp(target["at"], required=True)
    path = store.resolve_file(target["file"])
    operations = [
        op
        for op in engine.relations("file", path, cutoff)
        if op["strength"] == "confirmed" and op["op"] in ("write", "delete")
    ]
    limitations, timeline, actor_notes = [], [], []
    checked_refs = {}

    def refs(finding):
        found = set()
        for candidate in cited_refs(finding, store):
            if candidate not in checked_refs:
                try:
                    record, _ = store.source_record(candidate)
                    checked_refs[candidate] = record
                except (ValueError, OSError, TypeError):
                    checked_refs[candidate] = None
            record = checked_refs[candidate]
            if record and record["at"] is not None and record["at"] <= cutoff:
                found.add(record["ref"])
        return found

    def operation_refs(op):
        return {op["request"], op["result"]} - {None}

    def cite(ref):
        return store.handle("e", {"ref": ref})

    def actor_scope(op):
        return (
            store.handle(
                "s",
                {
                    "kind": "agent",
                    "key": op["agent"],
                    "at": iso(op["at"]),
                    "since": None,
                },
            )
            if op["agent"]
            else None
        )

    verified_operations = []
    for op in operations:
        try:
            for ref in operation_refs(op):
                if ref not in checked_refs:
                    checked_refs[ref] = store.source_record(ref)[0]
            verified_operations.append(op)
        except (ValueError, OSError) as exc:
            limitations.append({"operation": op["id"], "error": str(exc)})
    operations = verified_operations

    for node in nodes:
        if node["generated_context"]:
            continue
        valid = set(node["valid_refs"])
        observed = [
            r
            for ref in valid
            for r in store.rows("SELECT ref,at FROM records WHERE ref=?", (ref,))
            if r["at"] is not None
        ]
        if observed:
            timeline.append(
                {
                    "node": node["id"],
                    "cutoff": node["at"],
                    "first": iso(min(r["at"] for r in observed)),
                    "last": iso(max(r["at"] for r in observed)),
                    "evidence": [
                        cite(r["ref"])
                        for r in sorted(observed, key=lambda r: (r["at"], r["ref"]))
                    ],
                }
            )
        if node["kind"] != "agent" or node["role"] not in ("origin", "repaired"):
            continue
        cited_writes = [op for op in operations if valid & operation_refs(op)]
        actors = sorted({op["agent"] for op in cited_writes if op["agent"]})
        if actors and node["key"] not in actors:
            actor_notes.append(
                {
                    "node": node["id"],
                    "claimed_node_actor": node["key"],
                    "actual_actors": actors,
                    "operations": [
                        {
                            "id": op["id"],
                            "at": iso(op["at"]),
                            "actor_scope": actor_scope(op),
                            "evidence": [cite(r) for r in sorted(operation_refs(op))],
                        }
                        for op in cited_writes
                    ],
                    "note": "Cited native target writes were performed by another actor. Coordination responsibility is a separate claim; verify the node rather than rewriting its author automatically.",
                }
            )

    finding_refs = {f["id"]: refs(f) for f in document["findings"]}
    predecessors, additions = [], defaultdict(dict)
    for op in operations:
        try:
            outline = change_outline(change_payloads(store, op))
        except (ValueError, OSError, TypeError) as exc:
            limitations.append({"operation": op["id"], "error": str(exc)})
            continue
        removed, added = set(), set()
        for row in outline:
            if row["kind"] not in ("edit_delta", "native_patch"):
                continue  # A whole Write containing a line is NOT its introduction.
            in_hunk = False
            for line in row["text"].splitlines():
                if line.startswith("@@"):
                    in_hunk = True
                    continue
                if not in_hunk or line[:1] not in ("+", "-"):
                    continue
                fragment = line[1:].strip()
                # Navigation heuristic only: suppress braces/tiny generic tokens.
                if len(fragment) >= 16 and any(c.isalpha() for c in fragment):
                    (added if line[0] == "+" else removed).add(fragment)
        removed, added = removed - added, added - removed
        for fid, cited in finding_refs.items():
            if not cited.intersection(operation_refs(op)):
                continue
            matches = defaultdict(list)
            for fragment in sorted(removed):
                earlier = [
                    p
                    for p in additions[fragment].values()
                    if op["requested_at"] is not None and p["at"] <= op["requested_at"]
                ]
                if len(earlier) == 1 and not cited.intersection(
                    operation_refs(earlier[0])
                ):
                    matches[earlier[0]["id"]].append(fragment)
            for prior_id, fragments in matches.items():
                prior = additions[fragments[0]][prior_id]
                predecessors.append(
                    {
                        "finding": fid,
                        "file": path,
                        "fragments": fragments,
                        "current_operation": op["id"],
                        "current_actor": op["agent"],
                        "current_at": iso(op["at"]),
                        "current_evidence": [
                            cite(r) for r in sorted(operation_refs(op))
                        ],
                        "earlier_operation": prior_id,
                        "earlier_actor": prior["agent"],
                        "earlier_at": iso(prior["at"]),
                        "earlier_actor_scope": actor_scope(prior),
                        "earlier_evidence": [
                            cite(r) for r in sorted(operation_refs(prior))
                        ],
                        "not_author_proof": True,
                        "note": "Unique earlier native Edit/patch adding the same trimmed line in this index; not first authorship, continuous state, or causal proof. Open both originals.",
                    }
                )
        for fragment in added:
            additions[fragment][op["id"]] = op

    return {
        "timeline": sorted(timeline, key=lambda n: (n["first"], n["node"])),
        "actor_notes": actor_notes,
        "literal_predecessors": predecessors,
        "post_write_returns": post_write_returns(
            engine, operations, target, limitations
        ),
        "limitations": limitations,
        "semantic_verified": False,
        "note": "Target-file native facts and literal navigation hints only. Timeline is cited record time, not query cutoff or proof the claim occurred then. No prose verified, report changed, or causal edge added.",
    }
