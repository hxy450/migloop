"""Account for target call candidates, without pretending to infer their effects."""

from .store import timestamp


def reconcile(engine, target, document, explained):
    at, since = target["at"], target.get("since")
    key = engine.store.resolve_file(target["file"])
    request = {
        "op": "file",
        "key": key,
        "at": at,
        "since": since,
        "view": "calls",
        "limit": 100,
    }
    calls, offset = [], 0
    while offset is not None:
        part = engine.query({**request, "offset": offset})
        calls.extend(part["rows"])
        offset = part["next"]
    by_request = {}
    for effect in engine.relations("pool", None, timestamp(at, required=True)):
        by_request.setdefault(effect["request"], []).append(effect)
    dispositions, errors = {}, []
    for value in document.get("reviewed", []):
        if (
            not isinstance(value, dict)
            or set(value) != {"ref", "effect", "reason"}
            or value.get("effect") not in ("modified", "no_target_change", "unknown")
            or not isinstance(value.get("reason"), str)
            or not value["reason"].strip()
        ):
            raise ValueError(
                "reviewed requires ref, effect modified/no_target_change/unknown, and reason"
            )
        try:
            record, _ = engine.store.source_record(value["ref"])
            if record["ref"] in dispositions:
                errors.append({"ref": value["ref"], "error": "duplicate reviewed call"})
            dispositions[record["ref"]] = value
        except (ValueError, OSError) as error:
            errors.append({"ref": value["ref"], "error": str(error)})
    missing, covered, unknown, excluded = [], [], [], []
    for call in calls:
        names = {tool.casefold() for tool in call["tools"]}
        if names and names <= {"read", "read_file", "glob", "grep", "ls", "list_files"}:
            continue
        native = by_request.get(call["ref"], [])
        if (
            native
            and names
            <= {
                "read",
                "read_file",
                "write",
                "write_file",
                "edit",
                "multiedit",
                "delete_file",
            }
            and all(e["path"] != key or e["op"] == "read" for e in native)
        ):
            continue
        refs = {call["ref"]}
        refs.update(
            r["b"]
            for r in engine.store.rows(
                "SELECT p.b FROM pairs p JOIN records r ON r.ref=p.b WHERE p.a=? AND r.at<=?",
                (call["ref"], timestamp(at, required=True)),
            )
        )
        summary = {
            "ref": call["cite"],
            "at": call["at"],
            "tools": call["tools"],
            "summary": call["excerpt"],
            "recorded_effects": [e["op"] for e in native if e["path"] == key],
        }
        if refs.intersection(explained):
            covered.append(summary)
            continue
        assessment = next(
            (dispositions[ref] for ref in refs if ref in dispositions), None
        )
        if assessment is None:
            missing.append(summary)
        elif assessment["effect"] == "modified":
            errors.append(
                {
                    "ref": assessment["ref"],
                    "error": "modified call has no finding.changes attribution",
                }
            )
            missing.append(summary)
        elif assessment["effect"] == "unknown":
            unknown.append({**summary, "reason": assessment["reason"]})
        else:
            excluded.append({**summary, "reason": assessment["reason"]})
    return {
        "explained": covered,
        "unassessed": missing,
        "unknown": unknown,
        "model_excluded": excluded,
        "issues": errors,
        "note": "Call candidates are not confirmed modifications. Exclusions/reasons are model claims, not certified effects.",
    }
