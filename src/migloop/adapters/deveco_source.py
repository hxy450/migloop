"""Portable DevEco report input: native exports or frozen native event JSONLs.

Only the native payload is reconstructed; request/result projections of the
same part are counted once. No Claude-shaped messages or inferred parents.
"""
import json
from pathlib import Path


FORMAT = "deveco-events/1"


def normalize(document):
    info = dict(document["info"])
    info.setdefault("parentID", info.get("parent_id"))
    info.setdefault("time", {"created": info.get("time_created"), "updated": info.get("time_updated")})
    if isinstance(info.get("model"), str):
        try:
            info["model"] = json.loads(info["model"])
        except ValueError:
            pass
    if "tokens" not in info and "tokens_input" in info:
        info["tokens"] = {key: info.get("tokens_" + key) or 0 for key in ("input", "output", "reasoning")}
        info["tokens"]["cache"] = {key: info.get("tokens_cache_" + key) or 0 for key in ("read", "write")}
    return {"info": info, "messages": document["messages"]}


def load(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    if text.startswith("Exporting session:"):
        text = text.split("\n", 1)[1]
    try:
        document = json.loads(text)
    except ValueError:
        document = None
    if isinstance(document, dict) and isinstance(document.get("info"), dict) and isinstance(document.get("messages"), list):
        return normalize(document)
    first = json.loads(text.splitlines()[0])
    if not isinstance(first, dict) or first.get("format") != FORMAT or first.get("type") != "deveco_session":
        raise ValueError("not a DevEco session: " + str(path))
    sid = first["session"]["id"]
    messages, parts = {}, {}
    for row in map(json.loads, filter(str.strip, text.splitlines()[1:])):
        if row.get("format") != FORMAT or row.get("session", {}).get("id") != sid:
            raise ValueError("mixed DevEco sessions in " + str(path))
        if row.get("type") != "deveco_part":
            continue
        mid, pid = row["origin"]["message"], row["origin"]["part"]
        previous = messages.setdefault(mid, {})
        previous.update(row.get("message") or {})
        previous.setdefault("id", mid)
        rank = 0 if row.get("phase") == "request" else 1
        if (mid, pid) not in parts or rank >= parts[mid, pid][0]:
            parts[mid, pid] = (rank, row["part"])
    docs = [{"info": info, "parts": [part for (mid2, _), (_, part) in parts.items() if mid2 == mid]}
            for mid, info in messages.items()]
    return normalize({"info": first["info"], "messages": docs})


def descendants(path, root):
    """Only explicit parent IDs inside the supplied folder; never consult a host DB."""
    documents = {}
    for candidate in sorted(Path(path).parent.iterdir()):
        if candidate.suffix.lower() not in (".json", ".jsonl") or candidate.resolve() == Path(path).resolve():
            continue
        try:
            doc = load(candidate)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        sid = doc["info"].get("id")
        if sid in documents and documents[sid] != doc:
            raise ValueError("conflicting DevEco session exports: " + str(sid))
        documents[sid] = doc
    selected, seen = [], {root}
    while True:
        children = [doc for sid, doc in documents.items() if sid not in seen and doc["info"].get("parentID") in seen]
        if not children:
            return selected
        selected.extend(children)
        seen.update(doc["info"]["id"] for doc in children)


def child_rows(documents):
    rows, parts = [], {}
    for doc in documents:
        info, messages = doc["info"], doc["messages"]
        tokens = info.get("tokens")
        if not isinstance(tokens, dict):
            tokens = {key: sum((m["info"].get("tokens") or {}).get(key, 0) or 0 for m in messages
                              if m["info"].get("role") == "assistant") for key in ("input", "output", "reasoning")}
            tokens["cache"] = {key: sum(((m["info"].get("tokens") or {}).get("cache") or {}).get(key, 0) or 0
                                       for m in messages if m["info"].get("role") == "assistant") for key in ("read", "write")}
        times = info.get("time") or {}
        model = info.get("model")
        if isinstance(model, dict):
            model = model.get("id") or model.get("modelID")
        rows.append({"id": info["id"], "title": info.get("title") or "", "agent": info.get("agent") or "",
                     "model": model, "created": times.get("created"), "updated": times.get("updated"),
                     "tokens": {**{key: tokens.get(key) or 0 for key in ("input", "output", "reasoning")},
                                "cache_read": (tokens.get("cache") or {}).get("read") or 0,
                                "cache_write": (tokens.get("cache") or {}).get("write") or 0}})
        parts[info["id"]] = [part for message in messages for part in message.get("parts", [])]
    rows.sort(key=lambda row: (row["created"] or 0, row["id"]))
    return rows, parts
