"""Import once; query SQLite; expand the original bytes by a verified offset."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_FILE_TOKEN = re.compile(r"(?<![\w.])[\w@+-][\w@+.-]*\.[A-Za-z][A-Za-z0-9]{0,15}(?!\w)")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def timestamp(value, *, required=False):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return int(parsed.timestamp() * 1_000_000)
    except (ValueError, TypeError, AttributeError, OverflowError):
        if required:
            raise ValueError(
                "time must be a timezone-qualified ISO timestamp"
            ) from None
        return None


def iso(value):
    return (
        datetime.fromtimestamp(value / 1_000_000, timezone.utc).isoformat()
        if value is not None
        else None
    )


def path_key(value, cwd=""):
    value = value.replace("\\", "/")
    if not value.startswith("/") and not re.match(r"^[A-Za-z]:/", value):
        value = posixpath.join(cwd.replace("\\", "/"), value)
    return posixpath.normpath(value)


def flatten(value):
    if isinstance(value, dict):
        return "\n".join(str(k) + "\n" + flatten(v) for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(flatten(v) for v in value)
    return value if isinstance(value, str) else encode(value)


@dataclass(frozen=True)
class Source:
    path: str
    name: str
    agent: str | None = None
    cwd: str = ""
    protocol: str = "auto"


_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE sources(id TEXT PRIMARY KEY,name TEXT UNIQUE,path TEXT,agent TEXT,cwd TEXT,size INT,mtime INT);
CREATE TABLE records(ref TEXT PRIMARY KEY,source TEXT,line INT,offset INT,length INT,sha TEXT,
 at INT,kind TEXT,body TEXT,summary TEXT,native TEXT);
CREATE INDEX record_scope ON records(source,at,line);
CREATE INDEX record_time ON records(at);
CREATE INDEX record_native ON records(native);
CREATE TABLE mentions(name TEXT,record TEXT,PRIMARY KEY(name,record));
CREATE TEMP TABLE parts(record TEXT,source TEXT,slot INT,family TEXT,role TEXT,call_id TEXT,tool TEXT,
 payload TEXT,success INT,at INT,PRIMARY KEY(record,slot));
CREATE INDEX pair_calls ON parts(source,family,call_id);
CREATE TABLE pairs(a TEXT,b TEXT,PRIMARY KEY(a,b));
CREATE TABLE effects(id TEXT PRIMARY KEY,path TEXT,agent TEXT,op TEXT,strength TEXT,at INT,
 request TEXT,result TEXT,status TEXT,basis TEXT);
CREATE INDEX effect_path ON effects(path,at);
CREATE INDEX effect_agent ON effects(agent,at);
CREATE TABLE dispatches(id TEXT PRIMARY KEY,parent TEXT,child TEXT,at INT,request TEXT,result TEXT);
CREATE TABLE files(path TEXT PRIMARY KEY);
CREATE TABLE runs(id TEXT PRIMARY KEY,kind TEXT,request TEXT,data TEXT,body TEXT);
CREATE TABLE frames(run TEXT,offset INT,text TEXT,sha TEXT,PRIMARY KEY(run,offset));
CREATE TABLE visible(run TEXT,offset INT,complete INT,observed TEXT);
"""


def parts(record):
    """Only protocol-defined positions. Never parse code strings as executed calls."""
    blocks = (
        (record.get("message") or {}).get("content")
        if isinstance(record.get("message"), dict)
        else None
    )
    if isinstance(blocks, list):
        for slot, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                yield (
                    slot,
                    "cc",
                    "request",
                    block.get("id"),
                    block.get("name", ""),
                    block.get("input"),
                    None,
                )
            elif block.get("type") == "tool_result":
                error = block.get("is_error", False)
                success = int(not error) if isinstance(error, bool) else None
                metadata = record.get("toolUseResult")
                child = metadata.get("agentId") if isinstance(metadata, dict) else None
                yield (
                    slot,
                    "cc",
                    "result",
                    block.get("tool_use_id"),
                    "",
                    {"content": block.get("content"), "native_child_id": child},
                    success,
                )
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return
    kind = payload.get("type")
    if record.get("type") == "response_item":
        if kind in ("function_call", "custom_tool_call"):
            value = (
                payload.get("arguments")
                if kind == "function_call"
                else payload.get("input")
            )
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            yield (
                0,
                kind,
                "request",
                payload.get("call_id"),
                payload.get("name", ""),
                value,
                None,
            )
        elif kind in ("function_call_output", "custom_tool_call_output"):
            value = payload.get("output")
            success = None
            for container in (payload, value):
                if isinstance(container, dict):
                    if type(container.get("exit_code")) is int:
                        success = int(container["exit_code"] == 0)
                    if type(container.get("success")) is bool:
                        success = int(container["success"])
                    if type(container.get("is_error")) is bool:
                        success = int(not container["is_error"])
            yield (
                0,
                kind.removesuffix("_output"),
                "result",
                payload.get("call_id"),
                "",
                value,
                success,
            )
    if record.get("type") == "event_msg" and kind == "patch_apply_end":
        success = (
            int(payload["success"]) if type(payload.get("success")) is bool else None
        )
        yield (
            0,
            "patch",
            "patch",
            payload.get("call_id"),
            "apply_patch",
            payload.get("changes"),
            success,
        )


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise ValueError("index does not exist; import first")
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.create_function(
            "literal_contains",
            2,
            lambda body, needle: needle in body.casefold(),
            deterministic=True,
        )
        schema = self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if schema is None or schema[0] != "inquiry/1":
            self.db.close()
            raise ValueError("incomplete or incompatible index")

    def close(self):
        self.db.close()

    @classmethod
    def build(cls, path, sources):
        target = Path(path).resolve()
        sources = list(sources)
        if target.exists():
            raise ValueError("will not overwrite an existing index")
        if not sources or len({s.name for s in sources}) != len(sources):
            raise ValueError("sources must have unique nonempty logical names")
        if any(not s.name or s.protocol not in ("auto", "text") for s in sources):
            raise ValueError("invalid source registration")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive reservation: a failed import remains explicitly incomplete.
        with target.open("xb"):
            pass
        db = sqlite3.connect(target)
        db.row_factory = sqlite3.Row
        try:
            db.executescript(_SCHEMA)
            for source in sources:
                cls._import(db, source)
            cls._effects(db)
            db.execute("INSERT INTO meta VALUES(?,?)", ("schema", "inquiry/1"))
            db.commit()
        finally:
            db.close()
        return cls(target)

    @staticmethod
    def _import(db, source):
        path = Path(source.path).resolve()
        before = path.stat()
        sid = digest(source.name.encode())[:16]
        db.execute(
            "INSERT INTO sources VALUES(?,?,?,?,?,?,?)",
            (
                sid,
                source.name,
                str(path),
                source.agent,
                source.cwd,
                before.st_size,
                before.st_mtime_ns,
            ),
        )
        with path.open("rb") as stream:
            line = 0
            while True:
                offset = stream.tell()
                raw = stream.readline()
                if not raw:
                    break
                line += 1
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                try:
                    value = json.loads(text) if source.protocol != "text" else None
                except ValueError:
                    value = None
                record = value if isinstance(value, dict) else {}
                at = timestamp(record.get("timestamp"))
                kind = str(
                    record.get("type")
                    or ("text" if source.protocol == "text" else "unknown")
                )
                body = flatten(value) if value is not None else text
                message = record.get("message")
                main = (
                    message.get("content")
                    if isinstance(message, dict)
                    else record.get("payload", value)
                )
                summary = (flatten(main) if main is not None else text)[:260].replace(
                    "\n", " "
                )
                sha = digest(raw)
                ref = f"{sid}:{line}:{sha[:16]}"
                native = record.get("uuid")
                db.execute(
                    "INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        ref,
                        sid,
                        line,
                        offset,
                        len(raw),
                        sha,
                        at,
                        kind,
                        body,
                        summary,
                        native if isinstance(native, str) else None,
                    ),
                )
                db.executemany(
                    "INSERT OR IGNORE INTO mentions VALUES(?,?)",
                    [(name.casefold(), ref) for name in set(_FILE_TOKEN.findall(body))],
                )
                for slot, family, role, cid, tool, payload, success in parts(record):
                    db.execute(
                        "INSERT INTO parts VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            ref,
                            sid,
                            slot,
                            family,
                            role,
                            cid if isinstance(cid, str) and cid else None,
                            tool if isinstance(tool, str) else "",
                            encode(payload),
                            success,
                            at,
                        ),
                    )
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("source changed during import: " + source.name)

    @staticmethod
    def _effects(db):
        def effect(path, owner, op, strength, at, request, result, status, basis):
            if not isinstance(path, str) or not path:
                return
            normalized = path_key(path, owner["cwd"])
            identity = digest(encode([normalized, op, request, result]).encode())[:24]
            db.execute("INSERT OR IGNORE INTO files VALUES(?)", (normalized,))
            db.execute(
                "INSERT OR IGNORE INTO effects VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    normalized,
                    owner["agent"],
                    op,
                    strength,
                    at,
                    request,
                    result,
                    status,
                    basis,
                ),
            )

        sources = {s["id"]: s for s in db.execute("SELECT * FROM sources")}
        for request in db.execute("SELECT * FROM parts WHERE role='request'"):
            cid = request["call_id"]
            siblings = (
                db.execute(
                    "SELECT * FROM parts WHERE source=? AND family=? AND call_id=?",
                    (request["source"], request["family"], cid),
                ).fetchall()
                if cid
                else []
            )
            uses = [p for p in siblings if p["role"] == "request"]
            returns = [p for p in siblings if p["role"] == "result"]
            result = returns[0] if len(returns) == 1 and len(uses) == 1 else None
            ordered = (
                result is not None
                and request["at"] is not None
                and result["at"] is not None
                and (
                    request["at"],
                    int(request["record"].split(":")[1]),
                    request["slot"],
                )
                <= (result["at"], int(result["record"].split(":")[1]), result["slot"])
            )
            status = (
                "missing_id"
                if not cid
                else "ambiguous"
                if len(uses) > 1 or len(returns) > 1
                else "pending"
                if not result
                else "unordered_or_undated"
                if not ordered
                else "failed"
                if result["success"] == 0
                else "returned"
            )
            if ordered:
                db.execute(
                    "INSERT OR IGNORE INTO pairs VALUES(?,?)",
                    (request["record"], result["record"]),
                )
                db.execute(
                    "INSERT OR IGNORE INTO pairs VALUES(?,?)",
                    (result["record"], request["record"]),
                )
            data = json.loads(request["payload"])
            if not isinstance(data, dict):
                continue
            name = request["tool"].split(".")[-1].casefold()
            op = {
                "read": "read",
                "read_file": "read",
                "write": "write",
                "write_file": "write",
                "edit": "write",
                "multiedit": "write",
                "delete_file": "delete",
            }.get(name)
            owner = sources[request["source"]]
            if (
                name in ("task", "agent", "spawn_agent")
                and ordered
                and result["success"] != 0
            ):
                output = json.loads(result["payload"])
                if isinstance(output, str):
                    try:
                        output = json.loads(output)
                    except ValueError:
                        output = None
                child = (
                    (output.get("native_child_id") or output.get("agent_id"))
                    if isinstance(output, dict)
                    else None
                )
                matches = {
                    s["agent"]
                    for s in sources.values()
                    if s["agent"]
                    and isinstance(child, str)
                    and (s["agent"] == child or s["agent"].endswith(":" + child))
                }
                if len(matches) == 1 and owner["agent"]:
                    identity = digest(
                        encode([request["record"], result["record"], child]).encode()
                    )[:24]
                    db.execute(
                        "INSERT OR IGNORE INTO dispatches VALUES(?,?,?,?,?,?)",
                        (
                            identity,
                            owner["agent"],
                            next(iter(matches)),
                            result["at"],
                            request["record"],
                            result["record"],
                        ),
                    )
            if not op:
                continue
            # A copied CC record cannot certify one actor as its unique writer.
            copied = (
                db.execute(
                    "SELECT COUNT(DISTINCT s.agent) FROM records r JOIN sources s ON r.source=s.id "
                    "WHERE r.native=(SELECT native FROM records WHERE ref=?)",
                    (request["record"],),
                ).fetchone()[0]
                > 1
            )
            confirmed = ordered and result["success"] == 1 and not copied
            effect(
                data.get("file_path") or data.get("path"),
                owner,
                op,
                "confirmed" if confirmed else "candidate",
                result["at"] if ordered else request["at"],
                request["record"],
                result["record"] if ordered else None,
                "copied_owner" if copied else status,
                "native_tool",
            )
        for part in db.execute("SELECT * FROM parts WHERE role='patch'").fetchall():
            changes = json.loads(part["payload"])
            if isinstance(changes, dict):
                for path, detail in changes.items():
                    op = (
                        "delete"
                        if isinstance(detail, dict) and detail.get("type") == "delete"
                        else "write"
                    )
                    effect(
                        path,
                        sources[part["source"]],
                        op,
                        "confirmed"
                        if part["success"] == 1 and part["at"] is not None
                        else "candidate",
                        part["at"],
                        None,
                        part["record"],
                        "native_observation",
                        "patch_apply_end",
                    )

    def rows(self, sql, values=()):
        return [dict(row) for row in self.db.execute(sql, values)]

    def source_record(self, ref):
        rows = self.rows(
            "SELECT r.*,s.path,s.name,s.agent FROM records r JOIN sources s ON r.source=s.id WHERE ref=?",
            (ref,),
        )
        if not rows:
            raise ValueError("unknown original reference")
        record = rows[0]
        with Path(record["path"]).open("rb") as stream:
            stream.seek(record["offset"])
            raw = stream.read(record["length"])
        if digest(raw) != record["sha"]:
            raise ValueError("original bytes changed; reference no longer valid")
        return record, raw.decode("utf-8", errors="replace")

    def locate(self, source, line):
        if type(line) is not int or line < 1:
            raise ValueError("line must be a positive integer")
        rows = self.rows(
            "SELECT id FROM sources WHERE name=? OR path=?", (source, source)
        )
        if not rows:
            rows = [
                r
                for r in self.rows("SELECT id,name FROM sources")
                if Path(r["name"]).name == source
            ]
        if len(rows) != 1:
            raise ValueError("source missing or ambiguous; use its full logical name")
        records = self.rows(
            "SELECT ref FROM records WHERE source=? AND line=?", (rows[0]["id"], line)
        )
        if not records:
            raise ValueError("line does not exist")
        return records[0]["ref"]

    def resolve_file(self, key):
        if not isinstance(key, str) or not key:
            raise ValueError("file key required")
        normalized = path_key(key)
        candidates = [
            r["path"]
            for r in self.rows("SELECT path FROM files")
            if r["path"] == normalized or r["path"].endswith("/" + normalized)
        ]
        if len(candidates) > 1:
            raise ValueError("ambiguous file; use full path: " + ", ".join(candidates))
        return candidates[0] if candidates else normalized


def discover(pool):
    """Register native owners only. A directory hierarchy is never a dispatch edge."""
    root = Path(pool).resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in (
            ".jsonl",
            ".md",
            ".json",
            ".py",
            ".txt",
        ):
            continue
        agent, cwd = None, ""
        if path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                for _ in range(20):
                    line = stream.readline()
                    if not line:
                        break
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if obj.get("type") == "session_meta" and isinstance(
                        obj.get("payload"), dict
                    ):
                        agent = obj["payload"].get("id")
                        cwd = obj["payload"].get("cwd") or ""
                        break
                    if obj.get("sessionId"):
                        agent = (
                            str(obj["sessionId"])
                            + ":"
                            + str(obj.get("agentId") or "main")
                        )
                        cwd = obj.get("cwd") or ""
                        break
        yield Source(
            str(path),
            path.relative_to(root).as_posix(),
            agent,
            cwd,
            "auto" if path.suffix == ".jsonl" else "text",
        )
