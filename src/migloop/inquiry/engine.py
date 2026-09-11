"""One query contract and one plain-text transport, shared by MCP and the page."""

from __future__ import annotations

import difflib
import json
import posixpath
import uuid

from .store import Store, digest, encode, iso, timestamp


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

    def query(self, request):
        if not isinstance(request, dict):
            raise TypeError("query must be an object")
        op = request.get("op")
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
            return {
                "kind": "original",
                "ref": ref,
                "source": record["name"],
                "line": record["line"],
                "at": iso(record["at"]),
                "pointer": request.get("pointer"),
                "text": text,
                "chars": len(text),
                "complete_selected_text": True,
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
        if view not in ("records", "relations"):
            raise ValueError("view must be records or relations")
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
        if view == "relations":
            return {
                "kind": "relations",
                "scope": scope,
                "dispatches": dispatches,
                **self._page([self._relation(r) for r in relations], offset, limit),
            }
        table = " FROM records r JOIN sources s ON r.source=s.id WHERE " + where
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
                excerpt=text[start : start + 260].replace("\n", " ")
                if terms
                else summary,
                excerpt_offset=start if terms else None,
                chars=len(text),
                is_full_original=False,
            )
        return {
            "kind": "records",
            "scope": scope,
            "total": total,
            "rows": rows,
            "next": offset + len(rows) if offset + len(rows) < total else None,
            "related_operations": len(relations) if op != "search" else None,
            "undated_records": unknown_count,
            "dispatches": dispatches,
            "note": "Related records, not certified reads/writes. Unknown tool bodies remain searchable; open refs for originals.",
        }

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
        results = []
        for request in requests:
            try:
                results.append(
                    {"query": request, "ok": True, "data": self.query(request)}
                )
            except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
                results.append({"query": request, "ok": False, "error": str(exc)})
        body = "\n\n".join(self.render(i + 1, r) for i, r in enumerate(results))
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
                            "queries": requests,
                        }
                    ),
                    encode(results),
                    body,
                ),
            )
        return self.page(identity, 0)

    @staticmethod
    def render(number, result):
        if not result["ok"]:
            return f"[{number}] ERROR {result['error']}"
        data = result["data"]
        lines = [f"[{number}] {encode(result['query'])}"]
        if data["kind"] in ("original", "diff"):
            lines += [
                encode({k: v for k, v in data.items() if k != "text"}),
                data["text"],
            ]
        else:
            lines.append(encode({k: v for k, v in data.items() if k != "rows"}))
            for row in data.get("rows", []):
                if "excerpt" in row:
                    lines.append(
                        f"{row['ref']} {row['at'] or 'UNDATED'} {row['agent'] or 'UNKNOWN OWNER'} | {row['excerpt']}"
                    )
                else:
                    lines.append(encode(row))
        return "\n".join(lines)

    def page(self, identity, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be nonnegative")
        rows = self.store.rows(
            "SELECT body FROM runs WHERE id=? AND kind=?", (identity, "query")
        )
        if not rows or offset > len(rows[0]["body"]):
            raise ValueError("result or offset does not exist")
        body = rows[0]["body"]
        chunk = body[offset : offset + self.FRAME]
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
