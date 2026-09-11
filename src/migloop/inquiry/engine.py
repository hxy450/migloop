"""One query contract and one plain-text transport, shared by MCP and the page."""

from __future__ import annotations

import difflib
import json
import posixpath
import uuid
from functools import wraps

from .store import Store, digest, encode, iso, timestamp


def coordinate_transaction(method):
    @wraps(method)
    def query(self, request):
        if self.store.db.in_transaction:
            return method(self, request)
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            return method(self, request)

    return query


def content_text(raw):
    """Decode native content once; metadata remains available via pointer=''."""
    try:
        value = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(value, dict):
        return raw
    blocks = (
        (value.get("message") or {}).get("content")
        if isinstance(value.get("message"), dict)
        else None
    )
    if isinstance(blocks, list):
        texts = []
        for i, block in enumerate(blocks):
            if not isinstance(block, dict):
                texts.append(str(block))
                continue
            kind = block.get("type", "content")
            if kind == "tool_use":
                data = block.get("input")
                text = encode(data)
                if isinstance(data, dict):
                    text = "\n".join(
                        k + ": " + (v if isinstance(v, str) else encode(v))
                        for k, v in data.items()
                    )
                texts.append(f"BLOCK {i} tool={block.get('name')}\n{text}")
            else:
                data = block.get(
                    "content", block.get("text", block.get("thinking", block))
                )
                texts.append(
                    f"BLOCK {i} {kind}\n"
                    + (data if isinstance(data, str) else encode(data))
                )
        return "\n\n".join(texts)
    payload = value.get("payload")
    if isinstance(payload, dict):
        for key in ("output", "input", "arguments", "message", "content"):
            if key in payload:
                data = payload[key]
                return data if isinstance(data, str) else encode(data)
    return raw


def content_windows(text, terms, context):
    if (
        not isinstance(terms, list)
        or not 1 <= len(terms) <= 8
        or any(not isinstance(t, str) or not t or len(t) > 500 for t in terms)
    ):
        raise ValueError("open terms must be 1–8 literal strings of at most 500 chars")
    if type(context) is not int or not 0 <= context <= 50:
        raise ValueError("context must be 0–50 lines")
    lines = text.splitlines()
    ranges = []
    hits = 0
    for i, line in enumerate(lines):
        if any(t.casefold() in line.casefold() for t in terms):
            hits += 1
            start, end = max(0, i - context), min(len(lines), i + context + 1)
            if ranges and start <= ranges[-1][1]:
                ranges[-1][1] = max(end, ranges[-1][1])
            else:
                ranges.append([start, end])
    selected = "\n\n".join(
        f"CONTENT LINES {start + 1}–{end}\n" + "\n".join(lines[start:end])
        for start, end in ranges
    )
    return selected, {
        "matched_lines": hits,
        "content_line_ranges": [[a + 1, b] for a, b in ranges],
        "original_content_lines": len(lines),
        "selection": "literal windows, not whole record or absence proof",
    }


def bounds(request):
    at = timestamp(request.get("at"), required=True)
    since = (
        timestamp(request.get("since"), required=True)
        if request.get("since") is not None
        else None
    )
    if since is not None and since > at:
        raise ValueError("since is later than at")
    if type(request.get("undated", False)) is not bool:
        raise ValueError("undated must be boolean")
    return at, since


def in_scope(value, at, since, undated=False):
    return (
        undated if value is None else value <= at and (since is None or value >= since)
    )


def selected(value, pointer):
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("pointer must be a JSON Pointer")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list) and (
            not token.isascii() or not token.isdecimal() or str(int(token)) != token
        ):
            raise ValueError("array pointer requires a canonical nonnegative index")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


class Engine:
    FRAME = 6000

    def __init__(self, store: Store, *, session="diagnostic", origin="manual"):
        self.store = store
        self.session = session
        self.origin = origin

    def _where(self, request):
        at, since = bounds(request)
        clauses, values = ["r.at<=?"], [at]
        if since is not None:
            clauses.append("r.at>=?")
            values.append(since)
        time = "(" + " AND ".join(clauses) + ")"
        clauses = [
            f"({time} OR r.at IS NULL)" if request.get("undated", False) else time
        ]
        kind = (
            request["op"] if request["op"] != "search" else request.get("kind", "pool")
        )
        if kind not in ("file", "agent", "pool"):
            raise ValueError("scope kind must be file, agent or pool")
        key = request.get("key")
        if kind == "agent":
            if not isinstance(key, str) or not key:
                raise ValueError("agent key required")
            if not self.store.rows("SELECT id FROM sources WHERE agent=?", (key,)):
                raise ValueError("agent not registered")
            clauses.append("s.agent=?")
            values.append(key)
        if kind == "file":
            key = self.store.resolve_file(key)
            token = posixpath.basename(key).casefold()
            # Lexical associations are navigation only, not an inferred file operation.
            member = (
                "r.ref IN (SELECT record FROM mentions WHERE name=?)"
                if "." in token
                else "literal_contains(r.body,?)"
            )
            partner = (
                "o.ref IN (SELECT record FROM mentions WHERE name=?)"
                if "." in token
                else "literal_contains(o.body,?)"
            )
            clauses.append(
                "(" + member + " OR instr(lower(s.name),?)>0 OR "
                "r.ref IN (SELECT p.b FROM pairs p JOIN records o ON p.a=o.ref "
                "WHERE " + partner + " AND o.at<=?) OR "
                "r.ref IN (SELECT request FROM effects WHERE path=?) OR "
                "r.ref IN (SELECT result FROM effects WHERE path=? AND at<=?))"
            )
            values.extend([token, token, token, at, key, key, at])
        terms = request.get("terms", [])
        if (
            not isinstance(terms, list)
            or len(terms) > 8
            or any(not isinstance(t, str) or not t or len(t) > 500 for t in terms)
        ):
            raise ValueError(
                "terms must contain 0–8 nonempty literal strings, each <=500 chars"
            )
        if terms:
            clauses.append(
                "(" + " OR ".join("literal_contains(r.body,?)" for _ in terms) + ")"
            )
            values.extend(t.casefold() for t in terms)
        return (
            " AND ".join(clauses),
            values,
            {"kind": kind, "key": key, "at": iso(at), "since": iso(since)},
        )

    def relations(self, kind, key, at, since=None, undated=False):
        if kind not in ("file", "agent", "pool"):
            raise ValueError("invalid relationship scope")
        where, values = (
            ("path=?", [key])
            if kind == "file"
            else ("agent=?", [key])
            if kind == "agent"
            else ("1=1", [])
        )
        rows = self.store.rows(
            "SELECT e.*,r.at AS requested_at FROM effects e LEFT JOIN records r ON e.request=r.ref WHERE "
            + where,
            values,
        )
        result = []
        for row in rows:
            if in_scope(row["at"], at, since, undated):
                result.append(row)
            elif (
                row["at"] is not None
                and row["at"] > at
                and in_scope(row["requested_at"], at, since, undated)
            ):
                result.append(
                    {
                        **row,
                        "strength": "candidate",
                        "at": row["requested_at"],
                        "result": None,
                        "status": "not_returned_at_cutoff",
                    }
                )
        return sorted(result, key=lambda r: (r["at"] is None, r["at"] or 0, r["id"]))

    @coordinate_transaction
    def query(self, request):
        if not isinstance(request, dict):
            raise TypeError("query must be an object")
        op = request.get("op")
        if "scope" in request:
            scope = self.store.handle_value(request["scope"], "s")
            if any(k in request for k in ("key", "at", "since")):
                raise ValueError("use scope or explicit coordinates, not both")
            request = {k: v for k, v in request.items() if k != "scope"}
            request.update(
                {k: scope[k] for k in ("at", "since") if scope.get(k) is not None}
            )
            if op in ("file", "agent", "search", "blame"):
                request["key"] = scope["key"]
                if op == "search":
                    request["kind"] = scope["kind"]
                elif op not in (scope["kind"], "blame"):
                    raise ValueError("scope kind does not match operation")
        allowed = {
            "catalog": {"op", "kind", "q", "offset", "limit"},
            "file": {
                "op",
                "key",
                "at",
                "since",
                "undated",
                "offset",
                "limit",
                "terms",
                "view",
                "include_reads",
            },
            "agent": {
                "op",
                "key",
                "at",
                "since",
                "undated",
                "offset",
                "limit",
                "terms",
                "view",
                "include_reads",
            },
            "search": {
                "op",
                "kind",
                "key",
                "at",
                "since",
                "undated",
                "offset",
                "limit",
                "terms",
            },
            "open": {
                "op",
                "ref",
                "source",
                "line",
                "at",
                "since",
                "undated",
                "pointer",
                "terms",
                "context",
            },
            "diff": {
                "op",
                "before",
                "after",
                "before_pointer",
                "after_pointer",
                "at",
                "since",
                "undated",
            },
            "blame": {"op", "key", "at", "since", "undated"},
        }
        if op not in allowed or set(request) - allowed[op]:
            raise ValueError(
                "unknown operation or parameter; no legacy version/via parameters"
            )
        offset, limit = request.get("offset", 0), request.get("limit", 20)
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise ValueError("offset >=0 and limit 1–100 required")
        if op == "catalog":
            kind = request.get("kind", "agent")
            queries = {
                "agent": "SELECT DISTINCT agent AS key FROM sources WHERE agent IS NOT NULL",
                "file": "SELECT path AS key FROM files",
                "source": "SELECT name AS key,agent FROM sources",
            }
            if kind not in queries:
                raise ValueError("catalog kind must be agent/file/source")
            q = request.get("q", "")
            if not isinstance(q, str):
                raise ValueError("q must be literal text")
            rows = [
                r
                for r in self.store.rows(queries[kind])
                if q.casefold() in r["key"].casefold()
            ]
            return {
                "kind": "catalog",
                "catalog_kind": kind,
                **self._page(rows, offset, limit),
            }
        if op == "open":
            at, since = bounds(request)
            ref = request.get("ref")
            if ref and ("source" in request or "line" in request):
                raise ValueError("use ref or source+line, not both")
            if not ref:
                ref = self.store.locate(request.get("source"), request.get("line"))
            record, text = self.store.source_record(ref)
            if not in_scope(record["at"], at, since, request.get("undated", False)):
                raise ValueError("record outside requested time scope")
            if "pointer" in request:
                value = selected(json.loads(text), request["pointer"])
                text = value if isinstance(value, str) else encode(value)
            else:
                text = content_text(text)
            selection = {}
            if "terms" in request:
                text, selection = content_windows(
                    text, request["terms"], request.get("context", 6)
                )
            elif "context" in request:
                raise ValueError("context requires terms")
            owner_scope = (
                self.store.handle(
                    "s",
                    {
                        "kind": "agent",
                        "key": record["agent"],
                        "at": iso(at),
                        "since": None,
                    },
                )
                if record["agent"]
                else None
            )
            native = (
                [
                    r
                    for r in self.relations("agent", record["agent"], at)
                    if record["ref"] in (r["request"], r["result"])
                ]
                if record["agent"]
                else []
            )
            return {
                "kind": "original",
                "ref": ref,
                "cite": self.store.handle("e", {"ref": record["ref"]}),
                "source": record["name"],
                "line": record["line"],
                "at": iso(record["at"]),
                "record_owner": record["agent"],
                "record_owner_scope": owner_scope,
                "native_links": [self.link_view(r, iso(at)) for r in native[:8]],
                "native_links_total": len(native),
                "owner_note": "Transcript owner/caller, not automatically the author of quoted material. More links: agent(scope=record_owner_scope,view=relations).",
                "pointer": request.get("pointer"),
                "text": text,
                **selection,
                "chars": len(text),
                "complete_selected_text": True,
                "projection": "json_pointer"
                if "pointer" in request
                else 'native_content; pointer="" opens whole record',
            }
        if op == "diff":
            common = {k: request[k] for k in ("at", "since", "undated") if k in request}
            selections = []
            for side in ("before", "after"):
                args = {"op": "open", "ref": request[side], **common}
                if side + "_pointer" in request:
                    args["pointer"] = request[side + "_pointer"]
                selections.append(self.query(args))
            a, b = selections
            return {
                "kind": "diff",
                "before": a["ref"],
                "after": b["ref"],
                "note": "Explicit evidence text comparison, not a recovered file state or author.",
                "text": "\n".join(
                    difflib.unified_diff(
                        a["text"].splitlines(),
                        b["text"].splitlines(),
                        fromfile=a["ref"],
                        tofile=b["ref"],
                        lineterm="",
                    )
                ),
            }
        if op == "blame":
            at, since = bounds(request)
            key = self.store.resolve_file(request.get("key"))
            rows = [
                r
                for r in self.relations(
                    "file", key, at, since, request.get("undated", False)
                )
                if r["op"] != "read"
            ]
            return {
                "kind": "blame",
                "status": "not_proven",
                "file": key,
                "note": "This core does not replay unknown file history. These are recorded operations, not line authors.",
                "rows": [self._relation(r) for r in rows],
            }
        where, values, scope = self._where(request)
        view = request.get("view", "records")
        if view not in ("records", "relations", "calls", "inputs"):
            raise ValueError("view must be records, calls, relations or inputs")
        if view == "inputs" and op != "agent":
            raise ValueError("inputs is an agent view")
        if "include_reads" in request and (
            view != "calls" or type(request["include_reads"]) is not bool
        ):
            raise ValueError("include_reads is a boolean for view=calls only")
        scope_id = self.store.handle("s", scope)
        at, since = bounds(request)
        relations = (
            self.relations(
                scope["kind"], scope["key"], at, since, request.get("undated", False)
            )
            if op != "search"
            else []
        )
        dispatches = (
            self.store.rows(
                "SELECT * FROM dispatches WHERE (parent=? OR child=?) AND at<=?",
                (scope["key"], scope["key"], at),
            )
            if op == "agent"
            else []
        )
        dispatches = [
            {**d, "at": iso(d["at"])}
            for d in dispatches
            if since is None or d["at"] >= since
        ]
        if view in ("relations", "inputs") and request.get("terms"):
            matches = {
                r["ref"]
                for r in self.store.rows(
                    "SELECT r.ref FROM records r JOIN sources s ON r.source=s.id WHERE "
                    + where,
                    values,
                )
            }
            relations = [
                r
                for r in relations
                if matches.intersection({r["request"], r["result"]})
            ]
            dispatches = [
                d
                for d in dispatches
                if matches.intersection({d["request"], d["result"]})
            ]
        if view == "inputs":
            grouped = {}
            other = 0
            for relation in relations:
                if relation["op"] != "read":
                    continue
                if relation["strength"] != "confirmed" or not relation["result"]:
                    other += 1
                    continue
                group = grouped.setdefault(
                    relation["path"],
                    {"path": relation["path"], "deliveries": 0, "results": []},
                )
                group["deliveries"] += 1
                group["results"].append(
                    self.store.handle("e", {"ref": relation["result"]})
                )
            return {
                "kind": "inputs",
                "scope": scope,
                "scope_id": scope_id,
                **self._page(
                    sorted(grouped.values(), key=lambda g: g["path"]), offset, limit
                ),
                "other_read_operations": other,
                "note": "Confirmed native read returns, grouped by path. Not proof of full file delivery, attention or active context. Other reads: view=relations. Shell/dispatch/message inputs: records/search; zero here does not mean no input.",
            }
        if view == "relations":
            return {
                "kind": "relations",
                "scope": scope,
                "scope_id": scope_id,
                "dispatches": dispatches,
                **self._page(
                    [self.link_view(r, scope["at"]) for r in relations], offset, limit
                ),
            }
        table = " FROM records r JOIN sources s ON r.source=s.id WHERE " + where
        folded_reads = 0
        if view == "calls":
            table += " AND r.ref IN (SELECT record FROM calls)"
            if not request.get("include_reads", False):
                readonly = (
                    "r.ref NOT IN (SELECT record FROM calls WHERE read_basis IS NULL)"
                )
                folded_reads = self.store.db.execute(
                    "SELECT COUNT(*)" + table + " AND " + readonly, values
                ).fetchone()[0]
                table += " AND NOT (" + readonly + ")"
        unknown_where, unknown_values, _ = self._where({**request, "undated": True})
        unknown_count = self.store.db.execute(
            "SELECT COUNT(*) FROM records r JOIN sources s ON r.source=s.id WHERE r.at IS NULL AND "
            + unknown_where,
            unknown_values,
        ).fetchone()[0]
        total = self.store.db.execute("SELECT COUNT(*)" + table, values).fetchone()[0]
        rows = self.store.rows(
            "SELECT r.ref,r.at,r.kind,r.body,r.summary,s.name,s.agent,r.line"
            + table
            + " ORDER BY r.at IS NULL,r.at,s.name,r.line LIMIT ? OFFSET ?",
            [*values, limit, offset],
        )
        for row in rows:
            text = row.pop("body")
            summary = row.pop("summary")
            terms = request.get("terms") or (
                [posixpath.basename(scope["key"])] if scope["kind"] == "file" else []
            )
            positions = [text.casefold().find(t.casefold()) for t in terms]
            match = min((p for p in positions if p >= 0), default=0)
            start = max(0, match - 60)
            row.update(
                at=iso(row["at"]),
                excerpt=summary
                if view == "calls" or not terms or not any(p >= 0 for p in positions)
                else text[start : start + 260].replace("\n", " "),
                excerpt_offset=start if terms else None,
                chars=len(text),
                is_full_original=False,
                cite=self.store.handle("e", {"ref": row["ref"]}),
                agent_scope=self.store.handle(
                    "s",
                    {
                        "kind": "agent",
                        "key": row["agent"],
                        "at": scope["at"],
                        "since": None,
                    },
                )
                if row["agent"]
                else None,
                tools=[
                    c["tool"]
                    for c in self.store.rows(
                        "SELECT tool FROM calls WHERE record=?", (row["ref"],)
                    )
                ],
            )
            if view == "calls":
                row["read_basis"] = [
                    r["read_basis"]
                    for r in self.store.rows(
                        "SELECT read_basis FROM calls WHERE record=?", (row["ref"],)
                    )
                ]
                row["results"] = [
                    self.store.handle("e", {"ref": r["ref"]})
                    for r in self.store.rows(
                        "SELECT r.ref FROM pairs p JOIN records r ON r.ref=p.b WHERE p.a=? AND r.at<=? AND r.ref NOT IN (SELECT record FROM calls)",
                        (row["ref"], at),
                    )
                ]
                related = self.store.rows(
                    "SELECT r.body FROM pairs p JOIN records r ON p.b=r.ref WHERE p.a=? AND r.at<=?",
                    (row["ref"], at),
                )
                needle = (
                    posixpath.basename(scope["key"])
                    if scope["kind"] == "file"
                    else None
                )
                for other in related:
                    pos = (
                        other["body"].casefold().find(needle.casefold())
                        if needle
                        else -1
                    )
                    if pos >= 0:
                        row["excerpt"] += " | RESULT: " + other["body"][
                            max(0, pos - 30) : pos + len(needle) + 65
                        ].replace("\n", " ")
                        break
        participants = []
        if scope["kind"] == "file" and op != "search":
            for agent in sorted({r["agent"] for r in relations if r["agent"]}):
                own = [r for r in relations if r["agent"] == agent]
                written_at = max(
                    (
                        r["at"]
                        for r in own
                        if r["op"] == "write" and r["at"] is not None
                    ),
                    default=None,
                )
                last_write = next(
                    (
                        r
                        for r in reversed(own)
                        if r["op"] == "write" and r["at"] == written_at
                    ),
                    None,
                )
                input_at = last_write["requested_at"] if last_write else None
                participants.append(
                    {
                        "agent": agent,
                        "scope": self.store.handle(
                            "s",
                            {
                                "kind": "agent",
                                "key": agent,
                                "at": iso(written_at)
                                if written_at is not None
                                else scope["at"],
                                "since": None,
                            },
                        ),
                        "reads": sum(r["op"] == "read" for r in own),
                        "writes": sum(r["op"] != "read" for r in own),
                        "candidates": sum(r["strength"] == "candidate" for r in own),
                        "scope_basis": "latest recorded write in this view"
                        if written_at is not None
                        else "view cutoff",
                        "input_scope": self.store.handle(
                            "s",
                            {
                                "kind": "agent",
                                "key": agent,
                                "at": iso(input_at),
                                "since": None,
                            },
                        )
                        if input_at is not None
                        else None,
                    }
                )
        return {
            "kind": "records",
            "scope": scope,
            "scope_id": scope_id,
            "total": total,
            "rows": rows,
            "next": offset + len(rows) if offset + len(rows) < total else None,
            "related_operations": len(relations) if op != "search" else None,
            "undated_records": unknown_count,
            "dispatches": dispatches,
            "participants": participants,
            "folded_read_calls": folded_reads,
            "unfold": {**request, "include_reads": True, "offset": 0}
            if folded_reads
            else None,
            "note": "Related records, not certified reads/writes. Unknown tool bodies remain searchable; open refs for originals.",
        }

    def link_view(self, row, at):
        edge = self._relation(row)
        if row["op"] not in ("read", "write") or not row["agent"]:
            return edge
        agent = self.store.handle(
            "s",
            {
                "kind": "agent",
                "key": row["agent"],
                "at": iso(row["at"])
                if row["op"] == "write" and row["at"] is not None
                else at,
                "since": None,
            },
        )
        file = self.store.handle(
            "s",
            {
                "kind": "file",
                "key": row["path"],
                "at": iso(row["at"]) if row["at"] is not None else at,
                "since": None,
            },
        )
        origin, destination = (file, agent) if row["op"] == "read" else (agent, file)
        payload = {
            "relation": row["op"],
            "evidence": [r for r in (row["request"], row["result"]) if r],
            "operation": row["id"],
            "from_scope": origin,
            "to_scope": destination,
        }
        edge.update(
            link=self.store.handle("l", payload),
            from_scope=origin,
            to_scope=destination,
        )
        edge["request"] = (
            self.store.handle("e", {"ref": row["request"]}) if row["request"] else None
        )
        edge["result"] = (
            self.store.handle("e", {"ref": row["result"]}) if row["result"] else None
        )
        return edge

    @staticmethod
    def _page(rows, offset, limit):
        return {
            "total": len(rows),
            "rows": rows[offset : offset + limit],
            "next": offset + limit if offset + limit < len(rows) else None,
        }

    @staticmethod
    def _relation(row):
        return {
            k: iso(row[k]) if k == "at" else row[k]
            for k in (
                "id",
                "path",
                "agent",
                "op",
                "strength",
                "at",
                "request",
                "result",
                "status",
                "basis",
            )
        }

    def investigate(self, requests):
        if not isinstance(requests, list) or not 1 <= len(requests) <= 24:
            raise ValueError("batch must contain 1–24 queries")
        frames = []
        batch = uuid.uuid4().hex[:16]
        budget = max(40, self.FRAME // len(requests) - 225)
        for number, request in enumerate(requests, 1):
            results = []
            try:
                results.append(
                    {"query": request, "ok": True, "data": self.query(request)}
                )
            except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
                results.append({"query": request, "ok": False, "error": str(exc)})
            body = self.render(1, results[0])
            identity = uuid.uuid4().hex[:16]
            with self.store.db:
                self.store.db.execute(
                    "INSERT INTO runs VALUES(?,?,?,?,?)",
                    (
                        identity,
                        "query",
                        encode(
                            {
                                "session": self.session,
                                "origin": self.origin,
                                "queries": [request],
                                "batch": batch,
                                "item": number,
                            }
                        ),
                        encode(results),
                        body,
                    ),
                )
            frames.append(
                self.page(
                    identity, 0, _limit=self.FRAME if len(requests) == 1 else budget
                )
            )
        return "\n\n".join(frames)

    @staticmethod
    def render(number, result):
        if not result["ok"]:
            return f"[{number}] ERROR {result['error']}"
        data = result["data"]
        lines = [
            f"[{number}] {result['query'].get('op')} total={data.get('total', '-')} scope={data.get('scope_id', '-')}"
        ]
        lines.append("QUERY " + encode(result["query"]))
        if data["kind"] in ("original", "diff"):
            lines += [
                encode(
                    {
                        k: v
                        for k, v in data.items()
                        if k
                        not in (
                            "text",
                            "native_links",
                            "owner_note",
                            "ref",
                            "complete_selected_text",
                        )
                    }
                ),
                data["text"],
            ]
            for relation in data.get("native_links", []):
                lines.append(
                    "NATIVE_LINK "
                    + encode(
                        {
                            k: relation.get(k)
                            for k in ("link", "op", "path", "from_scope", "to_scope")
                        }
                    )
                )
        else:
            lines.append(
                encode(
                    {k: v for k, v in data.items() if k not in ("rows", "participants")}
                )
            )
            for actor in sorted(
                data.get("participants", []),
                key=lambda a: (not a["writes"], a["agent"]),
            ):
                lines.append(
                    ("WRITER " if actor["writes"] else "READER ")
                    + actor["agent"].split(":")[-1]
                    + f" scope={actor['scope']} writes={actor['writes']} reads={actor['reads']} candidates={actor['candidates']}"
                    + (
                        f" input_scope={actor['input_scope']} (agent view=inputs; before latest write request)"
                        if actor.get("input_scope")
                        else ""
                    )
                )
            for row in data.get("rows", []):
                if "excerpt" in row:
                    lines.append(
                        f"{row.get('cite', row['ref'])} {row['at'] or 'UNDATED'} {'/'.join(row.get('tools', []))} {row['agent'] or 'UNKNOWN OWNER'} owner_scope={row.get('agent_scope') or '-'} | {row['excerpt']}"
                        + (
                            f" results={encode(row['results'])}"
                            if row.get("results")
                            else ""
                        )
                    )
                else:
                    lines.append(encode(row))
        return "\n".join(lines)

    def page(self, identity, offset=0, *, _limit=None):
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be nonnegative")
        rows = self.store.rows(
            "SELECT body,request FROM runs WHERE id=? AND kind=?", (identity, "query")
        )
        if not rows or offset > len(rows[0]["body"]):
            raise ValueError("result or offset does not exist")
        if (
            self.origin == "mcp"
            and json.loads(rows[0]["request"])["session"] != self.session
        ):
            raise ValueError("result belongs to a different investigator")
        body = rows[0]["body"]
        # An emitted (result,offset) is immutable, including a short batch preview.
        saved = self.store.rows(
            "SELECT text FROM frames WHERE run=? AND offset=?", (identity, offset)
        )
        if saved:
            return saved[0]["text"]
        chunk = body[offset : offset + (_limit if _limit is not None else self.FRAME)]
        end = offset + len(chunk)
        next_offset = end if end < len(body) else None
        frame = (
            f"RESULT {identity} chars={len(body)} range={offset}:{end}\n"
            + chunk
            + f"\nEND FRAME next={next_offset if next_offset is not None else 'none'}; "
            "server_sent_only; not proof of model visibility or understanding"
        )
        with self.store.db:
            self.store.db.execute(
                "INSERT OR IGNORE INTO frames VALUES(?,?,?,?)",
                (identity, offset, frame, digest(frame.encode())),
            )
        return frame

    def observe_visibility(self, identity, offset, wrapper_text):
        """Harness-only observation. Not exposed as an MCP tool or model self-certification."""
        rows = self.store.rows(
            "SELECT text FROM frames WHERE run=? AND offset=?", (identity, offset)
        )
        if not rows:
            raise ValueError("frame was not emitted")
        complete = rows[0]["text"] in wrapper_text
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO visible VALUES(?,?,?,?)",
                (identity, offset, int(complete), wrapper_text),
            )
        return complete

    def trace(self, session=None):
        return [
            {
                "id": row["id"],
                **json.loads(row["request"]),
                "frames": self.store.rows(
                    "SELECT offset,sha FROM frames WHERE run=? ORDER BY offset",
                    (row["id"],),
                ),
                "visibility": self.store.rows(
                    "SELECT offset,complete FROM visible WHERE run=?", (row["id"],)
                ),
            }
            for row in self.store.rows(
                "SELECT id,request FROM runs WHERE kind='query' ORDER BY rowid"
            )
            if session is None or json.loads(row["request"])["session"] == session
        ]
