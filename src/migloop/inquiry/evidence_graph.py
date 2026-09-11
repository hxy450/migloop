"""Materialize cited native relations, not an inferred causal explanation.

Models supply node judgments. With edges omitted, the server places only
byte-checked indexed operations on the graph. Added endpoints stay neutral;
query order, copied summaries and lexical mentions never create connections.
"""

from .store import iso, timestamp


def attach(engine, finding, target):
    if "edges" in finding:
        return finding
    cutoff = timestamp(target["at"], required=True)
    nodes = [dict(node) for node in finding.get("nodes", [])]
    refs = set()
    for ref in [
        *finding.get("changes", []),
        *(ref for n in nodes for ref in n.get("evidence", [])),
    ]:
        try:
            record, _ = engine.store.source_record(ref)
            if record["at"] is not None and record["at"] <= cutoff:
                refs.add(record["ref"])
        except (ValueError, OSError, TypeError):
            pass  # The regular report checker diagnoses the original reference.

    def coordinates(node):
        if "scope" in node:
            return engine.store.handle_value(node["scope"], "s")
        return node

    def endpoint(kind, key, at, evidence):
        matches = []
        for node in nodes:
            value = coordinates(node)
            actual_key = (
                engine.store.resolve_file(value["key"])
                if value["kind"] == "file"
                else value["key"]
            )
            when = timestamp(value["at"], required=True)
            if value["kind"] == kind and actual_key == key and at <= when <= cutoff:
                matches.append((when, node))
        if matches:
            return min(matches, key=lambda item: item[0])[1]["id"]
        scope = engine.store.handle(
            "s", {"kind": kind, "key": key, "at": iso(at), "since": None}
        )
        identity = "recorded-" + scope
        while any(n.get("id") == identity for n in nodes):
            identity += "-event"
        nodes.append(
            {
                "id": identity,
                "scope": scope,
                "role": "context",
                "reason": "原生操作的证据端点；模型未对这个节点单独归因。",
                "evidence": evidence,
            }
        )
        return identity

    edges = []
    for operation in engine.relations("pool", None, cutoff):
        evidence = [ref for ref in (operation["request"], operation["result"]) if ref]
        if (
            operation["op"] not in ("read", "write")
            or not operation["agent"]
            or operation["at"] is None
            or not refs.intersection(evidence)
        ):
            continue
        # Both endpoints and the operation evidence are rechecked by report.check.
        agent = endpoint("agent", operation["agent"], operation["at"], evidence)
        file = endpoint("file", operation["path"], operation["at"], evidence)
        origin, destination = (
            (file, agent) if operation["op"] == "read" else (agent, file)
        )
        edges.append(
            {
                "from": origin,
                "to": destination,
                "link": engine.link_view(operation, target["at"])["link"],
                "claim": f"原生记录：{operation['op']} @ {iso(operation['at'])}；仅认证历史关系，不证明问题传播。",
            }
        )
    return {**finding, "nodes": nodes, "edges": edges}
