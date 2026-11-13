# -*- coding: utf-8 -*-
"""DeepSeek Harness (dsh) session logs on disk: location, decoding, lineage.

dsh stores one append-only log per Session under its persistence root
(``$DSH_HOME/sessions``, default ``~/.dsh/sessions``)::

    <root>/--<normalized cwd>--/<encoded session id>/session.v4.jsonl[.zstd]

The first row is the physical header (``{"type": "session", "version": 4,
"id", "createdAt", "cwd", "parentSession"?, "origin"?, ...}``); every later row
is one ``SessionEvent`` (``{"type", "seq", "time", "data", ...}``) with Unix
millisecond times. The default encoding is a concatenation of independent
Zstandard frames (one header frame, then one frame per append batch);
``compression: 'none'`` stores the same rows as plain lines.

Only the format version this module was written against is decoded; any other
header version is refused with :class:`UnsupportedSessionFormat` instead of
being guessed. Historical generations are migrated by dsh itself when a Session
is opened for writing.

Zstandard decoding uses, in order: ``compression.zstd`` (Python 3.14+), the
third-party ``zstandard`` module, or the ``node`` executable (Node >= 23.8 ships
zstd in ``node:zlib``; any dsh install has Node >= 24.9). ``node:zlib`` decodes
only the first frame of a concatenation, so frames are always located here and
decoded one by one. A torn final frame (crash during append) is skipped, as dsh
itself does.

Sub-agents are separate Sessions whose header names the parent in
``parentSession``; :func:`descendants` finds them by scanning headers under the
same root. No relationship is inferred from directory names or prose.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

SUPPORTED_VERSIONS = (4,)
FROZEN_FORMAT = "dsh-events/1"
ZSTD_MAGIC = 0xFD2FB528
_GENERATION_RE = re.compile(r"^session(?:\.v(\d+))?\.jsonl(\.zstd)?$")
_NODE_SCRIPT = (
    "const z=require('zlib');const c=[];process.stdin.on('data',d=>c.push(d));"
    "process.stdin.on('end',()=>{const b=Buffer.concat(c);const f=JSON.parse(process.argv[1]);"
    "for(const [s,e] of f){process.stdout.write(z.zstdDecompressSync(b.subarray(s,e)))}});"
)


class UnsupportedSessionFormat(ValueError):
    """The selected generation is a dsh format version this reader does not decode."""


class ZstdUnavailable(RuntimeError):
    """No Zstandard decoder is available for a compressed dsh log."""


# --------------------------------------------------------------------------- #
# Location
# --------------------------------------------------------------------------- #

def default_root():
    """``$DSH_SESSIONS_ROOT``, else ``$DSH_HOME/sessions``, else ``~/.dsh/sessions``."""
    explicit = os.environ.get("DSH_SESSIONS_ROOT")
    if explicit:
        return explicit
    home = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
    return os.path.join(home, "sessions")


def generation_of(name):
    """``(version, compressed)`` for a canonical generation file name, else None."""
    m = _GENERATION_RE.match(name)
    if not m:
        return None
    return int(m.group(1) or 0), bool(m.group(2))


def is_generation_file(path):
    return isinstance(path, str) and generation_of(os.path.basename(path)) is not None


def select_generation(session_dir):
    """Path of the numerically highest canonical generation in a session directory."""
    best = None
    try:
        names = os.listdir(session_dir)
    except OSError:
        return None
    for name in names:
        gen = generation_of(name)
        if gen is None or not os.path.isfile(os.path.join(session_dir, name)):
            continue
        if best is None or gen[0] > best[0]:
            best = (gen[0], os.path.join(session_dir, name))
    return best[1] if best else None


def resolve(path):
    """A generation file or a session directory -> the selected generation file, else None."""
    if not isinstance(path, str):
        return None
    if os.path.isdir(path):
        return select_generation(path)
    if os.path.isfile(path) and is_generation_file(path):
        return path
    return None


def root_of(generation_path):
    """``<root>`` for ``<root>/<project dir>/<session dir>/<generation file>``."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(generation_path))))


def iter_session_dirs(root):
    """Every ``<root>/<project dir>/<session dir>`` holding a canonical generation."""
    if not root or not os.path.isdir(root):
        return
    for project in sorted(os.listdir(root)):
        pdir = os.path.join(root, project)
        if not os.path.isdir(pdir) or project.startswith("."):
            continue
        for sess in sorted(os.listdir(pdir)):
            sdir = os.path.join(pdir, sess)
            if os.path.isdir(sdir) and select_generation(sdir):
                yield sdir


# --------------------------------------------------------------------------- #
# Zstandard
# --------------------------------------------------------------------------- #

def zstd_frames(buf):
    """Structurally complete frames ``[(start, end)]``; stops at a torn tail."""
    frames, off, size = [], 0, len(buf)
    while off < size:
        start = off
        if size - off < 4:
            break                                   # torn tail
        if int.from_bytes(buf[off:off + 4], "little") != ZSTD_MAGIC:
            raise ValueError("not a Zstandard dsh log: invalid frame magic at byte %d" % off)
        if size - off < 5:
            break
        off += 4
        desc = buf[off]
        off += 1
        fcs, single = desc >> 6, bool(desc & 0x20)
        checksum, dict_flag = bool(desc & 0x04), desc & 0x03
        off += (0 if single else 1) + (4 if dict_flag == 3 else dict_flag) + \
            ((1 if single else 0) if fcs == 0 else 1 << fcs)
        torn = False
        while True:
            if size - off < 3:
                torn = True
                break
            header = int.from_bytes(buf[off:off + 3], "little")
            off += 3
            block_type = (header >> 1) & 3
            if block_type == 3:
                raise ValueError("corrupt Zstandard session log: reserved block type")
            payload = 1 if block_type == 1 else header >> 3
            if size - off < payload:
                torn = True
                break
            off += payload
            if header & 1:
                break
        if torn:
            break
        if checksum:
            off += 4
        if off > size:
            break
        frames.append((start, off))
    return frames


def _decode_frames_python(buf, frames):
    try:
        from compression import zstd as stdlib_zstd   # Python 3.14+
        return b"".join(stdlib_zstd.decompress(buf[s:e]) for s, e in frames)
    except ImportError:
        pass
    try:
        import zstandard   # optional third-party module
    except ImportError:
        return None
    out = []
    for s, e in frames:
        out.append(zstandard.ZstdDecompressor().decompressobj().decompress(buf[s:e]))
    return b"".join(out)


def _decode_frames_node(buf, frames):
    node = os.environ.get("DSH_NODE") or shutil.which("node")
    if not node:
        return None
    proc = subprocess.run([node, "-e", _NODE_SCRIPT, json.dumps(frames)], input=buf,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    if proc.returncode != 0:
        raise ZstdUnavailable("node zstd decode failed: " + proc.stderr.decode("utf-8", "replace")[-400:])
    return proc.stdout


def decompress(buf, frames=None):
    """Decode a concatenated-frame dsh log; frames default to all complete frames."""
    frames = zstd_frames(buf) if frames is None else frames
    if not frames:
        return b""
    data = _decode_frames_python(buf, frames)
    if data is None:
        data = _decode_frames_node(buf, frames)
    if data is None:
        raise ZstdUnavailable(
            "this dsh log is Zstandard-compressed; install the 'zstandard' module, use Python 3.14+, "
            "or put Node.js (>= 23.8) on PATH")
    return data


def read_text(path, first_frame_only=False):
    with open(path, "rb") as fh:
        buf = fh.read()
    if not path.endswith(".zstd"):
        return buf.decode("utf-8", "replace")
    frames = zstd_frames(buf)
    if first_frame_only:
        frames = frames[:1]
    return decompress(buf, frames).decode("utf-8", "replace")


# --------------------------------------------------------------------------- #
# Decoding
# --------------------------------------------------------------------------- #

def _rows(text):
    """Parsed rows; an incomplete final line (torn raw append) is discarded."""
    lines = text.split("\n")
    complete = text.endswith("\n")
    rows = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            if i == len(lines) - 1 and not complete:
                break
            raise ValueError("malformed dsh session row %d" % (i + 1))
        rows.append(row)
    return rows


def check_header(header, path=""):
    if not isinstance(header, dict) or header.get("type") != "session" or not header.get("id"):
        raise ValueError("not a dsh session log (missing session header): %s" % path)
    if header.get("version") not in SUPPORTED_VERSIONS:
        raise UnsupportedSessionFormat(
            "dsh session format v%s is not supported (this reader decodes v%s); open it once in the "
            "matching dsh so it migrates, or update the adapter: %s"
            % (header.get("version"), "/".join(map(str, SUPPORTED_VERSIONS)), path))
    return header


def read_header(path):
    """The validated header of one generation without decoding the event body."""
    gen = resolve(path) or path
    text = read_text(gen, first_frame_only=True)
    first = text.split("\n", 1)[0]
    return check_header(json.loads(first) if first.strip() else None, gen)


def peek_header(path):
    """Header of a candidate file, or None when it is not a readable dsh log."""
    try:
        return read_header(path)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return None


def read_session(path):
    """``(header, events, generation_path)`` for one Session (file or directory)."""
    gen = resolve(path)
    if not gen:
        raise ValueError("not a dsh session log or session directory: %s" % path)
    rows = _rows(read_text(gen))
    if not rows:
        raise ValueError("empty dsh session log: %s" % gen)
    header = check_header(rows[0], gen)
    events = [r for r in rows[1:] if isinstance(r, dict) and isinstance(r.get("type"), str)]
    return header, events, gen


_NODE_HEADERS = (
    "const fs=require('fs'),z=require('zlib');const out={};"
    "for(const p of JSON.parse(process.argv[1])){try{const b=fs.readFileSync(p);"
    "const t=z.zstdDecompressSync(b).toString('utf8');out[p]=t.split('\\n',1)[0]}catch(e){}}"
    "process.stdout.write(JSON.stringify(out));"
)


def peek_headers(paths):
    """``{path: header}`` for many generations; compressed ones share one decoder call.

    ``zstdDecompressSync`` on a whole multi-frame file returns exactly the first
    frame, which is the header frame, so no frame scan is needed here.
    """
    out, pending = {}, []
    for p in paths:
        if p.endswith(".zstd") and _decode_frames_python(b"", []) is None:
            pending.append(p)
        else:
            header = peek_header(p)
            if header:
                out[p] = header
    node = os.environ.get("DSH_NODE") or shutil.which("node")
    for i in range(0, len(pending), 200):
        chunk = pending[i:i + 200]
        firsts = {}
        if node:
            try:
                proc = subprocess.run([node, "-e", _NODE_HEADERS, json.dumps(chunk)], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, timeout=300)
                firsts = json.loads(proc.stdout.decode("utf-8", "replace") or "{}") if proc.returncode == 0 else {}
            except (OSError, ValueError, subprocess.SubprocessError):
                firsts = {}
        for p in chunk:
            try:
                out[p] = check_header(json.loads(firsts[p]), p)
            except (KeyError, ValueError):
                continue
    return out


def header_index(root):
    """``{session id: (header, generation path)}`` for every readable Session under root."""
    gens = [select_generation(sdir) for sdir in iter_session_dirs(root)]
    index = {}
    for gen, header in peek_headers([g for g in gens if g]).items():
        index[header["id"]] = (header, gen)
    return index


def descendants(root, session_id, index=None):
    """Sub-agent Sessions below ``session_id`` (recursive), ordered by creation time."""
    index = header_index(root) if index is None else index
    out, frontier, seen = [], [session_id], {session_id}
    while frontier:
        parent = frontier.pop(0)
        kids = sorted((v for v in index.values() if v[0].get("parentSession") == parent),
                      key=lambda v: (v[0].get("createdAt") or 0, v[0]["id"]))
        for header, gen in kids:
            if header["id"] in seen:
                continue
            seen.add(header["id"])
            out.append((header, gen))
            frontier.append(header["id"])
    return out


def find_sessions(root, prefix):
    """Root-level Sessions whose id (or id without ``session-``) starts with ``prefix``."""
    hits = []
    for sid, (header, gen) in header_index(root).items():
        bare = sid[len("session-"):] if sid.startswith("session-") else sid
        if sid.startswith(prefix) or bare.startswith(prefix):
            hits.append((header, gen))
    return hits


# --------------------------------------------------------------------------- #
# Event helpers shared by adapters
# --------------------------------------------------------------------------- #

def iso(ms):
    if not isinstance(ms, (int, float)) or isinstance(ms, bool):
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def text_of(content):
    """Joined text blocks of a message ``content`` list (or a plain string)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


def tool_arguments(raw):
    """Decoded ``tool/call.arguments`` (the raw JSON string the model produced)."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {"_raw": raw}
    return value if isinstance(value, dict) else {"_value": value}


_SUBAGENT_RESULT_RE = re.compile(r"^started subagent (\S+)$")


def started_child(result_text):
    """Child id from the ``subagent`` tool's fixed result template (``started subagent <id>``)."""
    m = _SUBAGENT_RESULT_RE.match((result_text or "").strip())
    return m.group(1) if m else None


def catalog_children(events):
    """``{child id: subagent/catalog data}`` recorded by this Session."""
    out = {}
    for ev in events:
        if ev.get("type") == "subagent/catalog" and isinstance(ev.get("data"), dict):
            cid = ev["data"].get("childId")
            if isinstance(cid, str):
                out[cid] = ev["data"]
    return out


# --------------------------------------------------------------------------- #
# Frozen export (immutable JSONL material for evidence/inquiry kernels)
# --------------------------------------------------------------------------- #

def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def inherited_cut(header, events):
    """Seq of the last tagged ``session/end-seed`` marker of a fork child, else None."""
    if not header.get("isSeeded"):
        return None
    cut = None
    for ev in events:
        if ev.get("type") == "session/end-seed" and (ev.get("data") or {}).get("inherited") is True:
            cut = ev.get("seq")
    return cut


def frozen_rows(header, events, generation_path):
    """Lossless ``dsh-events/1`` rows: a session row, then one row per native event.

    ``uuid`` is the event's native identity ``<owner session>#<seq>``. A fork
    child's inherited prefix keeps the parent as owner, so copies of one parent
    event in several children are recognisable as copies, not new writes.
    """
    session = {"id": header["id"], "cwd": header.get("cwd") or "", "parent": header.get("parentSession"),
               "origin": header.get("origin")}
    cut = inherited_cut(header, events)
    yield {"format": FROZEN_FORMAT, "type": "dsh_session", "session": session,
           "timestamp": iso(header.get("createdAt")), "header": header,
           "origin": {"session": header["id"], "generation": os.path.basename(generation_path)}}
    for ev in events:
        seq = ev.get("seq")
        inherited = cut is not None and isinstance(seq, int) and seq < cut and header.get("parentSession")
        owner = header["parentSession"] if inherited else header["id"]
        yield {"format": FROZEN_FORMAT, "type": "dsh_event", "session": session,
               "timestamp": iso(ev.get("time")), "seq": seq, "uuid": "%s#%s" % (owner, seq), "event": ev,
               "origin": {"session": header["id"], "seq": seq, "inherited": bool(inherited)}}


def freeze_tree(path, destination, root=None):
    """Freeze one root Session and its sub-agent descendants as ``dsh-events/1`` JSONL.

    Layout: ``<destination>/<root id>.jsonl`` and
    ``<destination>/<root id>/subagents/<child id>.jsonl``. Returns the manifest.
    """
    import hashlib
    first = resolve(path)
    if not first:
        raise ValueError("not a dsh session log or session directory: %s" % path)
    root = root or root_of(first)
    destination = os.path.abspath(destination)
    stats, trees = {}, []

    def load(gen_path, rel_of):
        stats[gen_path] = os.stat(gen_path)
        with open(gen_path, "rb") as fh:
            source_sha = hashlib.sha256(fh.read()).hexdigest()
        h, ev, g = read_session(gen_path)
        trees.append((h, ev, g, rel_of(h), source_sha))
        return h

    header = load(first, lambda h: h["id"] + ".jsonl")
    for _child, cgen in descendants(root, header["id"]):
        load(cgen, lambda h: "%s/subagents/%s.jsonl" % (header["id"], h["id"]))
    targets = [os.path.join(destination, *t[3].split("/")) for t in trees]
    clash = [t for t in targets if os.path.exists(t)]
    if clash:
        raise ValueError("frozen material must be new; will not overwrite: %s" % clash[0])
    sources = []
    for (h, ev, g, rel, source_sha), target in zip(trees, targets):
        data = ("\n".join(_encoded(r) for r in frozen_rows(h, ev, g)) + "\n").encode("utf-8")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(data)
        sources.append({"name": rel, "session": h["id"], "parent": h.get("parentSession"),
                        "generation": g, "source_sha256": source_sha,
                        "sha256": hashlib.sha256(data).hexdigest(), "events": len(ev)})
    for g, before in stats.items():
        after = os.stat(g)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("dsh session log changed while freezing (session still running?): %s" % g)
    return {"format": FROZEN_FORMAT, "root_session": header["id"], "sessions_root": root, "sources": sources}
