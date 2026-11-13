"""DeepSeek Harness (dsh) sessions frozen as ``dsh-events/1`` JSONL.

dsh keeps one append-only log per Session (``session.v4.jsonl[.zstd]``); the
freezer (``dsh_export``) writes one row per native ``SessionEvent``, verbatim
under ``event``, with the Session identity and an ISO timestamp taken from the
event's own millisecond ``time``. Sub-agent Sessions are separate files whose
identity names the parent Session.

Requests and results are separate native events (``tool/call`` before
``tool/result``), so a request projection never contains future output. The
``subagent`` tool records no structured child id in its result; the child id is
read only from the tool's fixed result template (``started subagent <id>``),
never from prose, and becomes a dispatch only when a source with that identity
exists in the pool.
"""
import json
import re

from .base import Identity, message_role

FORMAT = "dsh-events/1"
_STARTED = re.compile(r"^started subagent (\S+)$")


def _text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(b["text"] for b in content
                     if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))


def _arguments(raw):
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except ValueError:
        return raw


class DshAdapter:
    name = "dsh"

    def matches(self, record):
        return record.get("format") == FORMAT

    def identity(self, record):
        session = record.get("session") or {}
        if session.get("id"):
            return Identity(self.name, session["id"], session.get("cwd") or "", session.get("parent"))

    def input_role(self, record):
        event = record.get("event") or {}
        kind, data = event.get("type"), event.get("data") or {}
        if kind == "user/message":
            return message_role({"role": "user", "content": data.get("content")})
        if kind in ("system/message", "developer/message"):
            message = data.get("message") or {}
            return message_role({"role": kind.split("/")[0], "content": message.get("content")})
        return None

    def parts(self, record):
        event = record.get("event") or {}
        kind, data = event.get("type"), event.get("data") or {}
        if kind == "tool/call":
            yield (0, "dsh", "request", data.get("callId"), data.get("name") or "",
                   _arguments(data.get("arguments")), None)
        elif kind == "tool/result":
            message = data.get("message") or {}
            error = message.get("isError")
            success = int(not error) if isinstance(error, bool) else None
            text = _text(message.get("content"))
            started = _STARTED.match(text.strip())
            yield (0, "dsh", "result", message.get("toolCallId"), "",
                   {"content": message.get("content"), "meta": data.get("meta"),
                    "native_child_id": started.group(1) if started else None}, success)
