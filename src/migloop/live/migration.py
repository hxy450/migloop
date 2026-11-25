"""``migloop <迁移工程目录> --live``:盯一次迁移的全部会话,外加会话总览。

迁移的分析单位是一个鸿蒙工程目录(会话总览 chain.py 同一口径):Claude 主迁移和中途新开的会话
(``<CLAUDE_CONFIG_DIR>/projects/<目录编码>/*.jsonl``,所有 ``~/.claude*`` 根都找)、cwd 落在目录里的
Codex rollout、``<目录>/.ecat`` 下的 ECAT 角色会话(按 ``.migbot/ecat_runs`` 的 run / 轮次挂上)。

- 每次刷新先重新列一遍目录找新会话:只列目录、读新文件的首行认身份,不解析内容;
- 每个会话交给它自己的增量监控(Claude:IncrementalSessionMonitor,Codex:CodexLiveMonitor),
  只读新追加的字节,状态随 checkpoint 落盘,重启接着读;
- 总览数据由各会话的增量状态拼出来,刷新时不整份重新解析;某个会话的完整分析页在点进去时才建;
- DevEco / dsh 会话这一版没有增量监控:目录里有就在总览里列出、标「不支持实时」。

停止时生成最终自包含页面:总览(数据内嵌)+ 每个会话一份完整分析页(放在同名 ``.sessions`` 目录)。
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import threading
import time
import urllib.parse
import webbrowser
from contextlib import suppress
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import ecat
from ..adapters import codex as _codex
from ..adapters.claude import STAGE_LABELS, ms_between
from .codexlive import CodexLiveMonitor
from .monitor import LIVE_HTML, IncrementalSessionMonitor, _atomic_write, _attach_live_controls, _now_iso

UNSUPPORTED = "不支持实时"


# --------------------------------------------------------------------------- #
# 目标 → 迁移目录
# --------------------------------------------------------------------------- #

def claude_slug(path: str) -> str:
    """Claude Code 的项目目录编码:绝对路径里非字母数字的字符都换成 ``-``。"""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def claude_project_roots(extra: Optional[str] = None) -> List[str]:
    """会话可能落盘的 projects 根:显式给的、$CLAUDE_CONFIG_DIR、~/.claude*/projects。"""
    roots: List[str] = []
    if extra:
        roots.append(extra)
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        roots.append(os.path.join(env, "projects"))
    home = os.path.expanduser("~")
    with suppress(OSError):
        for name in sorted(os.listdir(home)):
            if name.startswith(".claude") and os.path.isdir(os.path.join(home, name, "projects")):
                roots.append(os.path.join(home, name, "projects"))
    out: List[str] = []
    for r in roots:
        if os.path.normcase(os.path.abspath(r)) not in {os.path.normcase(os.path.abspath(x)) for x in out}:
            out.append(r)
    return out


def _first_cwd(path: str) -> Optional[str]:
    """Claude transcript 开头几百条里第一条带 cwd 的记录。"""
    with suppress(OSError), open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh):
            if n > 500:
                break
            with suppress(ValueError):
                rec = json.loads(line)
                if isinstance(rec, dict) and rec.get("cwd"):
                    return str(rec["cwd"])
    return None


def harmony_of_session(path: str, fmt: str) -> Optional[str]:
    """一个会话所在的迁移目录:ECAT 角色会话是 ``.ecat`` 的上一级,否则是会话的 cwd。"""
    found = ecat.harmony_of(path)
    if found:
        return found
    if fmt == "codex":
        return (_codex.session_summary(path) or {}).get("cwd")
    return _first_cwd(path)


def _under(harmony: str, cwd: Any) -> bool:
    """cwd 落在迁移目录里(含目录本身)。"""
    if not cwd:
        return False
    root = os.path.normcase(os.path.realpath(harmony))
    real = os.path.normcase(os.path.realpath(str(cwd)))
    with suppress(ValueError):
        return os.path.commonpath([real, root]) == root
    return False


# --------------------------------------------------------------------------- #
# 监控
# --------------------------------------------------------------------------- #

_ROLLOUT = re.compile(r"^rollout-.*\.jsonl$")


class MigrationMonitor:
    """一次迁移的全部会话。``poll_once`` = 列目录找新会话 + 各会话读增量。"""

    def __init__(self, harmony: str, focus: Optional[str] = None, cache_dir: Optional[str] = None,
                 poll_interval: float = 10.0, reset_cache: bool = False,
                 claude_root: Optional[str] = None, codex_root: Optional[str] = None,
                 deveco_root: Optional[str] = None, dsh_root: Optional[str] = None):
        self.harmony = os.path.abspath(harmony)
        self.focus = os.path.abspath(focus) if focus else None
        self.cache_dir = cache_dir
        self.poll_interval = max(0.2, float(poll_interval))
        self.reset_cache = reset_cache
        slug = claude_slug(self.harmony)
        self.claude_dirs = [os.path.join(r, slug) for r in claude_project_roots(claude_root)]
        if self.focus and self.focus.endswith(".jsonl") and not ecat.role_of(self.focus):
            here = os.path.dirname(self.focus)
            if os.path.normcase(here) not in {os.path.normcase(d) for d in self.claude_dirs}:
                self.claude_dirs.append(here)
        self.codex_root = codex_root or _codex.default_root()
        self.deveco_root = deveco_root
        self.dsh_root = dsh_root
        self.slots: Dict[str, Dict[str, Any]] = {}
        self._codex_seen: Dict[str, bool] = {}
        self._dsh_seen: Dict[str, Optional[Dict[str, Any]]] = {}
        self._stream_tids: Dict[str, Optional[str]] = {}
        self._history: Dict[str, Any] = {}
        self._heads: Dict[str, Any] = {}
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.version = 0
        self.last_update: Optional[str] = None
        self.last_error: Optional[str] = None
        self.timing = {"scan_s": 0.0, "poll_s": 0.0}

    # ---------- 发现 ----------
    def _add(self, key: str, path: str, fmt: str, live: bool, **extra: Any) -> bool:
        if key in self.slots:
            return False
        slot = {"key": key, "path": path, "format": fmt, "live": live, "role": "", "dimension": None,
                "monitor": None, **extra}
        if live:
            factory = CodexLiveMonitor if fmt == "codex" else IncrementalSessionMonitor
            slot["monitor"] = factory(path, cache_dir=self.cache_dir, poll_interval=self.poll_interval,
                                      reset_cache=self.reset_cache)
        self.slots[key] = slot
        return True

    def _scan_claude(self) -> bool:
        changed = False
        paths: List[str] = []
        for d in self.claude_dirs:
            with suppress(OSError):
                paths.extend(os.path.join(d, n) for n in os.listdir(d) if n.endswith(".jsonl"))
        paths.extend(ecat._iter_transcripts(self.harmony))
        if self.focus and self.focus.endswith(".jsonl") and os.path.isfile(self.focus) \
                and not _ROLLOUT.match(os.path.basename(self.focus)):
            paths.append(self.focus)
        for p in paths:
            key = os.path.splitext(os.path.basename(p))[0]
            role = ecat.role_of(p) or ""
            changed = self._add(key, os.path.abspath(p), "claude", True, role=role) or changed
        return changed

    def _scan_codex(self) -> bool:
        changed = False
        if not self.codex_root or not os.path.isdir(self.codex_root):
            return False
        for dirpath, _dirs, names in os.walk(self.codex_root):
            for name in names:
                if not _ROLLOUT.match(name):
                    continue
                path = os.path.abspath(os.path.join(dirpath, name))
                ours = self._codex_seen.get(path)
                if ours is None:
                    summary = _codex.session_summary(path)
                    if summary is None:
                        continue   # 首行还没写完,下轮再看
                    source = summary.get("source")
                    child = summary.get("thread_source") == "subagent" or (
                        isinstance(source, dict) and "subagent" in source)
                    ours = (not child) and _under(self.harmony, summary.get("cwd"))
                    self._codex_seen[path] = ours
                if ours:
                    tid = ecat._rollout_tid(path) or os.path.splitext(name)[0]
                    changed = self._add("cx-" + tid, path, "codex", True) or changed
        return changed

    def _scan_deveco(self) -> bool:
        from ..adapters import deveco
        db = deveco._find_db(self.deveco_root)
        if not db:
            return False
        changed = False
        with suppress(sqlite3.Error):
            conn = sqlite3.connect("file:///" + os.path.abspath(db).replace("\\", "/") + "?mode=ro", uri=True)
            try:
                rows = conn.execute("SELECT id, directory, title, time_created FROM session "
                                    "WHERE parent_id IS NULL").fetchall()
            finally:
                conn.close()
            for sid, directory, title, created in rows:
                if _under(self.harmony, directory):
                    changed = self._add("dv-" + sid, "DEVECO:" + sid, "deveco", False, title=title or "",
                                        started_at=_ms_iso(created)) or changed
        return changed

    def _scan_dsh(self) -> bool:
        from ..adapters import dsh_source
        root = self.dsh_root or dsh_source.default_root()
        if not root or not os.path.isdir(root):
            return False
        want = re.sub(r"[^a-z0-9]+", "", self.harmony.lower())
        changed = False
        with suppress(OSError):
            for project in os.listdir(root):
                if want not in re.sub(r"[^a-z0-9]+", "", project.lower()):
                    continue
                pdir = os.path.join(root, project)
                for sess in os.listdir(pdir):
                    sdir = os.path.join(pdir, sess)
                    if sdir not in self._dsh_seen:
                        gen = dsh_source.select_generation(sdir)
                        self._dsh_seen[sdir] = dsh_source.peek_header(gen) if gen else None
                    header = self._dsh_seen[sdir]
                    if header and not header.get("parentSession") and _under(self.harmony, header.get("cwd")):
                        changed = self._add("dsh-" + str(header["id"]), sdir, "dsh", False,
                                            started_at=_ms_iso(header.get("createdAt"))) or changed
        return changed

    def scan(self) -> bool:
        """列目录找新会话(只读新文件的首行认身份)。"""
        changed = self._scan_claude()
        changed = self._scan_codex() or changed
        changed = self._scan_deveco() or changed
        changed = self._scan_dsh() or changed
        return changed

    # ---------- 刷新 ----------
    def poll_once(self) -> bool:
        with self.lock:
            t0 = time.perf_counter()
            changed = self.scan()
            t1 = time.perf_counter()
            for slot in list(self.slots.values()):
                mon = slot.get("monitor")
                if mon is None:
                    continue
                try:
                    changed = bool(mon.poll_once()) or changed
                except Exception as exc:  # 一个会话读坏了不拖垮整页
                    self.last_error = "%s: %s: %s" % (slot["key"], type(exc).__name__, exc)
            self.timing = {"scan_s": round(t1 - t0, 3), "poll_s": round(time.perf_counter() - t1, 3)}
            if changed:
                self.version += 1
                self.last_update = _now_iso()
            return changed

    def _loop(self) -> None:
        while not self.stop_event.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception as exc:  # 保留上一版状态
                self.last_error = "%s: %s" % (type(exc).__name__, exc)

    def start(self) -> None:
        self.poll_once()
        self.thread = threading.Thread(target=self._loop, name="migloop-migration-live", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=max(2.0, self.poll_interval * 2))
        for slot in self.slots.values():
            if slot.get("monitor") is not None:
                with suppress(Exception):
                    slot["monitor"].save_checkpoint(force=True)

    # ---------- ECAT 挂接 ----------
    def _runs(self) -> List[Dict[str, Any]]:
        """``.migbot/ecat_runs/run_*``:每次 run 的熵记录与各轮角色流的 thread id(只读首行)。"""
        base = Path(self.harmony) / ".migbot" / "ecat_runs"
        runs: List[Dict[str, Any]] = []
        if not base.is_dir():
            return runs
        for d in sorted(p for p in base.glob("run_*") if p.is_dir()):
            hist_file = d / "entropy_history.jsonl"
            sig = _sig(str(hist_file))
            cached = self._history.get(str(d))
            if cached is None or cached[0] != sig:
                cached = (sig, ecat._load_history(d))
                self._history[str(d)] = cached
            hist = cached[1]
            binds: Dict[str, Dict[str, Any]] = {}
            for stream in sorted(d.glob("*/*.stream.jsonl")):
                slot_name, role = stream.parent.name, stream.name.split(".")[0]
                if slot_name.isdigit() and role in ecat.ROLES:
                    entry = {"role": role, "iteration": int(slot_name), "dimension": None}
                elif slot_name == "transcripts" and role.startswith("judge_"):
                    entry = {"role": "judge", "iteration": None, "dimension": role[len("judge_"):]}
                else:
                    continue
                tid = self._stream_tid(str(stream))
                if tid:
                    prev = binds.setdefault(tid, {**entry, "iterations": []})
                    if entry["iteration"] is not None and entry["iteration"] not in prev["iterations"]:
                        prev["iterations"].append(entry["iteration"])
            runs.append({"run_id": d.name, "start": hist[0].get("started_at") if hist else None,
                         "iterations": [{"iteration": r["iteration"], "total_H": r.get("total_H"),
                                         "breakdown": r.get("breakdown") or {}} for r in hist],
                         "binds": binds})
        return runs

    def _stream_tid(self, path: str) -> Optional[str]:
        if path not in self._stream_tids or self._stream_tids[path] is None:
            tid = None
            with suppress(OSError, ValueError), open(path, encoding="utf-8", errors="replace") as fh:
                first = json.loads(fh.readline() or "null")
                if isinstance(first, dict) and first.get("subtype") == "init" and first.get("session_id"):
                    tid = str(first["session_id"]).lower()
            self._stream_tids[path] = tid
        return self._stream_tids[path]

    def _head(self, path: str) -> Dict[str, Any]:
        """ECAT 会话开头的轮次 / 判官维度 / 循环角色(只读文件头一次)。"""
        if path not in self._heads:
            self._heads[path] = {"iteration": ecat._head_iteration(path),
                                 "dimension": ecat.judge_dimension(path), "loop": ecat.loop_role(path)}
        return self._heads[path]

    # ---------- 总览 ----------
    def overview(self, href: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None) -> Dict[str, Any]:
        """chain.html 用的总览数据(与 chain.build_chain 同形),全部来自各会话的增量状态。"""
        from ..chain import identity
        href = href or (lambda slot: "s/%s/" % urllib.parse.quote(slot["key"]))
        with self.lock:
            slots = list(self.slots.values())
            runs = self._runs()
        threads: Dict[str, Dict[str, Any]] = {}
        for slot in slots:
            threads[slot["key"]] = _thread(slot, href(slot) if slot["live"] else None)
        sessions: List[Dict[str, Any]] = []
        by_run: Dict[str, List[Dict[str, Any]]] = {}
        orphans: List[Dict[str, Any]] = []
        run_starts = sorted((r["start"], r["run_id"]) for r in runs if r["start"])
        for slot in slots:
            t = threads[slot["key"]]
            tid = slot["key"][3:] if slot["key"].startswith("cx-") else None
            bind = next(((r["run_id"], r["binds"][tid]) for r in runs if tid and tid in r["binds"]), None)
            if bind:
                t.update(role=bind[1]["role"], dimension=bind[1]["dimension"],
                         ecat_iterations=sorted(bind[1]["iterations"]))
                by_run.setdefault(bind[0], []).append(t)
                continue
            if slot["role"]:
                head = self._head(slot["path"])
                t.update(role=slot["role"], ecat_iterations=[head["iteration"]] if head["iteration"] is not None else [])
                rid = _run_at(run_starts, t.get("started_at"))
                (by_run.setdefault(rid, []) if rid else orphans).append(t)
                continue
            if slot["live"] and slot["format"] == "codex":
                head = self._head(slot["path"])
                if head["dimension"] or head["loop"]:
                    t.update(role="judge" if head["dimension"] else head["loop"], dimension=head["dimension"])
                    orphans.append(t)
                    continue
            sessions.append({"session_id": slot["key"], "kind": "session", "role": "",
                             "name": slot.get("title") or "", "started_at": t.get("started_at"),
                             "state": UNSUPPORTED if not slot["live"] else t.get("status"),
                             "threads": [t], "timeline": []})
        for run in runs:
            mine = by_run.get(run["run_id"]) or []
            sessions.append({"session_id": run["run_id"], "kind": "ecat", "role": "ecat", "name": run["run_id"],
                             "started_at": run["start"] or min((str(t.get("started_at") or "") for t in mine), default=""),
                             "threads": mine, "timeline": []})
        if orphans:
            sessions.append({"session_id": "ecat", "kind": "ecat", "role": "ecat", "name": "run 目录未登记的 ECAT 会话",
                             "started_at": min((str(t.get("started_at") or "") for t in orphans), default=""),
                             "threads": orphans, "timeline": []})
        sessions.sort(key=lambda s: str(s.get("started_at") or ""))
        flat = [t for s in sessions for t in s["threads"]]
        found = [t for t in flat if t.get("transcript")]
        summed = ("requests", "input_tokens", "cache_read_tokens", "output_tokens", "tool_calls",
                  "tool_failed", "agents", "agents_with_transcript", "aborted_agents")
        totals: Dict[str, Any] = {k: sum(t.get(k) or 0 for t in found) for k in summed}
        totals.update(sessions=len(sessions), threads=len(flat), threads_missing=0,
                      unsupported=sum(1 for t in flat if t.get("unsupported")))
        started = [t["started_at"] for t in found if t.get("started_at")]
        ended = [t["ended_at"] for t in found if t.get("ended_at")]
        focus_key = next((s["key"] for s in slots if self.focus and os.path.normcase(s["path"]) == os.path.normcase(self.focus)), "")
        return {
            **identity(self.harmony),
            "anchor": focus_key or os.path.basename(self.harmony), "harmony": self.harmony,
            "started_at": min(started, default=None), "ended_at": max(ended, default=None),
            "sessions": sessions, "totals": totals,
            "ecat_runs": [{"run_id": r["run_id"], "iterations": r["iterations"]} for r in reversed(runs)],
            "findings": [{"session_id": s["session_id"], "thread_id": t["thread_id"],
                          "role": t.get("dimension") or t.get("role") or s["kind"], **f}
                         for s in sessions for t in s["threads"] for f in t.get("findings") or []],
            "live": {"version": self.version, "last_update": self.last_update, "last_error": self.last_error,
                     "interval_s": self.poll_interval, **self.timing},
        }


def _sig(path: str) -> Optional[tuple]:
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _ms_iso(value: Any) -> Optional[str]:
    if not isinstance(value, (int, float)):
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _run_at(run_starts: List[tuple], started: Any) -> Optional[str]:
    """CC 线 ECAT 会话归哪次 run:开工时刻落在 [本 run 首条熵记录, 下一 run 首条熵记录) 里。"""
    if not started:
        return None
    hit = None
    for start, rid in run_starts:
        if str(started) >= str(start):
            hit = rid
    return hit


def _label(stage: Any) -> str:
    stage = str(stage or "")
    if stage.startswith("wf:"):
        return stage[3:]
    if stage == "unmarked":
        return "未标记"
    return STAGE_LABELS.get(stage, stage)


def _thread(slot: Dict[str, Any], href: Optional[str]) -> Dict[str, Any]:
    """一个会话 → 总览里的一格(chain.summarize 同形),取自增量状态。"""
    base = {"thread_id": slot["key"], "transcript": slot["path"], "role": slot.get("role") or "",
            "dimension": slot.get("dimension"), "ecat_iterations": [], "href": href,
            "format": slot["format"], "findings": [], "prompts": [], "stages": []}
    mon = slot.get("monitor")
    if mon is None:
        base.update(unsupported=True, status=UNSUPPORTED, started_at=slot.get("started_at"),
                    ended_at=None, duration_ms=0, model=None)
        return base
    snap = mon.snapshot()
    started, ended = snap.get("started_at"), snap.get("ended_at")
    agents = snap.get("agents") or []
    hist = snap.get("stage_history") or []
    stages = []
    for k, h in enumerate(hist):
        nxt = hist[k + 1] if k + 1 < len(hist) else None
        end = (nxt or {}).get("start_ts") or ended
        stages.append({"label": _label(h.get("stage")), "start_ts": h.get("start_ts") or started, "end_ts": end,
                       "duration_ms": ms_between(h.get("start_ts") or started, end) or 0,
                       "tool_calls": int(((nxt or {}).get("tools_at_start") if nxt else snap.get("tool_calls")) or 0)
                       - int(h.get("tools_at_start") or 0),
                       # 按派发计;老 checkpoint 没记派发数的段给 None(页面显示「—」)
                       "agents": None if "agents_at_start" not in h else
                       int(((nxt or {}).get("agents_at_start") if nxt else snap.get("agent_dispatches")) or 0)
                       - int(h.get("agents_at_start") or 0)})
    base.update(
        model=snap.get("model"), started_at=started, ended_at=ended,
        duration_ms=ms_between(started, ended) or 0,
        requests=snap.get("requests") or 0, input_tokens=snap.get("input_tokens") or 0,
        cache_read_tokens=snap.get("cache_read_tokens") or 0, output_tokens=snap.get("output_tokens") or 0,
        tool_calls=snap.get("tool_calls") or 0, tool_failed=snap.get("tool_failures") or 0,
        # 子代理按派发计(与离线页同口径),有转录的另报
        agents=max(int(snap.get("agent_dispatches") or 0), len(agents)), agents_with_transcript=len(agents),
        aborted_agents=sum(1 for a in agents if a.get("status") in ("interrupted", "failed")),
        stages=stages, prompts=[{"ts": p.get("ts"), "text": p.get("text") or ""} for p in snap.get("prompt_log") or []],
        status=snap.get("status"), current_stage=_label(snap.get("current_stage")),
        records=snap.get("records") or 0, version=snap.get("version") or 0)
    return base


# --------------------------------------------------------------------------- #
# 页面
# --------------------------------------------------------------------------- #

def overview_html(data: Optional[Dict[str, Any]] = None, live: Optional[Dict[str, Any]] = None) -> str:
    """会话总览页:``data`` 内嵌(最终页),或 ``live`` = {url, poll_ms} 轮询增量状态。"""
    from ..render import load_asset
    boot = json.dumps({"inline": data} if data is not None else {"live": live}, ensure_ascii=False)
    boot = boot.replace("</", "<\\/")
    page = load_asset("chain.html").replace("__CHAIN_ID__", "null")
    return '<script>window.__MIGLOOP_CHAIN__=%s;</script>\n%s' % (boot, page)


class _MigrationHandler(BaseHTTPRequestHandler):
    server_version = "MigLoopLive/2.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, body: Any, ctype: str, status: int = HTTPStatus.OK, headers: Optional[Dict[str, str]] = None) -> None:
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, etag: Optional[str] = None) -> None:
        if etag and self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self._send(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "application/json; charset=utf-8",
                   headers={"ETag": etag} if etag else None)

    def do_GET(self) -> None:
        srv: MigrationHTTPServer = self.server  # type: ignore[assignment]
        route = urllib.parse.urlsplit(self.path).path
        try:
            if route in ("/", "/index.html"):
                self._send(srv.overview_page, "text/html; charset=utf-8")
                return
            if route == "/api/overview":
                self._json(srv.migration.overview(), '"%d"' % srv.migration.version)
                return
            m = re.match(r"^/s/([^/]+)(/.*)?$", route)
            if m:
                self._session(urllib.parse.unquote(m.group(1)), m.group(2) or "")
                return
            self._send("not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)
        except Exception as exc:  # 服务不能因为一个请求崩
            self._send("请求失败: %s" % exc, "text/plain; charset=utf-8", HTTPStatus.INTERNAL_SERVER_ERROR)

    def _session(self, key: str, rest: str) -> None:
        srv: MigrationHTTPServer = self.server  # type: ignore[assignment]
        slot = srv.migration.slots.get(key)
        if slot is None or not slot["live"]:
            self._send("没有这个会话,或它%s" % UNSUPPORTED, "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)
            return
        if rest == "":
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", "/s/%s/" % urllib.parse.quote(key))
            self.end_headers()
            return
        mon = slot["monitor"]
        if rest in ("/", "/index.html"):
            self._send(srv.session_page(key), "text/html; charset=utf-8")
        elif rest == "/api/state":
            state = mon.snapshot()
            self._json(state, '"%s"' % state.get("version", 0))
        elif rest == "/status.html":
            self._send(srv.status_page, "text/html; charset=utf-8")
        elif rest == "/refresh":
            srv.session_page(key, rebuild=True)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "./")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif rest in ("/export.html", "/snapshot.html"):
            headers = {"Content-Disposition": 'attachment; filename="migloop-%s.html"' % key[:12]} \
                if rest == "/export.html" else None
            self._send(srv.build_report(slot["path"]), "text/html; charset=utf-8", headers=headers)
        elif rest == "/api/chat/config":
            chat = srv.chat_for(key)
            self._send(json.dumps(chat.info() if chat else {"enabled": False, "provider": "off", "model": None},
                                  ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send("not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        srv: MigrationHTTPServer = self.server  # type: ignore[assignment]
        m = re.match(r"^/s/([^/]+)/api/chat$", urllib.parse.urlsplit(self.path).path)
        chat = srv.chat_for(urllib.parse.unquote(m.group(1))) if m else None
        if chat is None:
            self._send(json.dumps({"error": "分析助手未启用"}, ensure_ascii=False),
                       "application/json; charset=utf-8", HTTPStatus.SERVICE_UNAVAILABLE)
            return
        try:
            size = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(size).decode("utf-8")) if 0 < size <= 256 * 1024 else {}
            reply = chat.chat(payload.get("messages"))
            self._send(json.dumps({"reply": reply, **chat.info()}, ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as exc:
            self._send(json.dumps({"error": "分析失败：%s" % exc}, ensure_ascii=False),
                       "application/json; charset=utf-8", HTTPStatus.BAD_GATEWAY)


class MigrationHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple, migration: MigrationMonitor, build_report: Callable[[str], bytes],
                 chat_factory: Optional[Callable[[str], Any]] = None):
        super().__init__(address, _MigrationHandler)
        self.migration = migration
        self.build_report = build_report
        self.chat_factory = chat_factory
        poll_ms = max(200, int(migration.poll_interval * 1000))
        self.poll_ms = poll_ms
        self.overview_page = overview_html(live={"url": "api/overview", "poll_ms": poll_ms})
        self.status_page = LIVE_HTML.replace("__MIGLOOP_POLL_MS__", str(poll_ms))
        self._pages: Dict[str, bytes] = {}
        self._chats: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def session_page(self, key: str, rebuild: bool = False) -> bytes:
        """某个会话的完整分析页:点进去时才建,之后用缓存,「刷新完整分析」才重建。"""
        with self._lock:
            if rebuild or key not in self._pages:
                slot = self.migration.slots[key]
                base = slot["monitor"].snapshot()
                chat = self.chat_for(key)
                self._pages[key] = _attach_live_controls(
                    self.build_report(slot["path"]), base.get("version"), base.get("records"), self.poll_ms,
                    chat.info() if chat else None)
            return self._pages[key]

    def chat_for(self, key: str) -> Any:
        if self.chat_factory is None or key not in self.migration.slots:
            return None
        if key not in self._chats:
            self._chats[key] = self.chat_factory(self.migration.slots[key]["path"])
        return self._chats[key]


def _stop_signal(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt


_CTRL_CLOSE_EVENT = 2
_console_handler: Any = None      # ctypes 回调要一直留着引用


class Stopper:
    """停止流程的两个状态:``stopping`` 已开始停止(不再打断主线程),``done`` 最终页已写完。"""

    def __init__(self) -> None:
        self.stopping = threading.Event()
        self.done = threading.Event()

    def on_console_close(self, interrupt: Callable[[], None], wait: float = 60.0) -> bool:
        """关控制台窗口:系统等处理函数返回后就结束进程(最多等几秒)。所以让主线程按 Ctrl+C 的路径停下,
        这里一直等到最终页写完再返回。"""
        if not self.stopping.is_set():
            interrupt()
        self.done.wait(wait)
        return True


def install_stop_signals(stopper: Optional[Stopper] = None) -> None:
    """Windows 上 Ctrl+Break 走 SIGBREAK、关控制台窗口走 CTRL_CLOSE_EVENT,默认都是直接结束进程、
    不写最终页。Ctrl+Break 改成和 Ctrl+C 一样从 serve_forever 退出;关窗口见 ``Stopper.on_console_close``。"""
    global _console_handler
    import signal
    if not hasattr(signal, "SIGBREAK"):
        return
    with suppress(ValueError, OSError):   # 只能在主线程装
        signal.signal(signal.SIGBREAK, _stop_signal)
    if stopper is None:
        return
    with suppress(Exception):
        import _thread
        import ctypes
        from ctypes import wintypes

        def on_ctrl(kind: int) -> bool:
            if kind != _CTRL_CLOSE_EVENT:
                return False                  # Ctrl+C / Ctrl+Break 交给上面的 signal 处理
            return stopper.on_console_close(_thread.interrupt_main)

        # 后注册的先被调用:排在 C 运行库的处理函数前面
        _console_handler = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)(on_ctrl)
        ctypes.WinDLL("kernel32").SetConsoleCtrlHandler(_console_handler, True)


def _say(text: str) -> None:
    with suppress(OSError, ValueError):       # 控制台窗口已关时 print 会失败,不能挡住写最终页
        print(text, flush=True)


def write_final(migration: MigrationMonitor, out_path: str, build_report: Callable[[str], bytes],
                build_trace: Optional[Callable[[str], Dict[str, Any]]] = None) -> str:
    """最终自包含页面:总览(数据内嵌)+ 每个会话一份完整分析页(``<out>.sessions/``)。"""
    out_path = os.path.abspath(out_path)
    stem = os.path.splitext(os.path.basename(out_path))[0]
    sess_dir = os.path.join(os.path.dirname(out_path), stem + ".sessions")
    os.makedirs(sess_dir, exist_ok=True)
    findings: Dict[str, List[Dict[str, Any]]] = {}
    live_slots = [s for s in list(migration.slots.values()) if s["live"]]
    for slot in live_slots:
        slot["_final"] = stem + ".sessions/" + re.sub(r"[^A-Za-z0-9_.-]", "_", slot["key"]) + ".html"
    def write_overview() -> None:
        # 只链到已经写好的分析页:中途被结束也不会有断链
        data = migration.overview(href=lambda slot: slot.get("_final") if slot.get("_final_written") else None)
        data["live"] = None
        _atomic_write(out_path, overview_html(data=data))

    # 先写总览(很快):关窗口只给几秒,至少总览在;各会话的完整分析页随后逐个写,写好一个就补上它的链接
    write_overview()
    for slot in live_slots:
        name = os.path.basename(slot["_final"])
        try:
            _atomic_write(os.path.join(sess_dir, name), build_report(slot["path"]), binary=True)
            slot["_final_written"] = True
            write_overview()
            if build_trace is not None:
                from .. import audit
                findings[slot["key"]] = audit.build_audit(build_trace(slot["path"]))["findings"]
        except Exception as exc:  # noqa: BLE001 - 一份建不出不拖垮最终页
            slot["_final_error"] = str(exc)
    data = migration.overview(href=lambda slot: slot.get("_final"))
    for s in data["sessions"]:
        for t in s["threads"]:
            t["findings"] = findings.get(t["thread_id"], [])
    data["findings"] = [{"session_id": s["session_id"], "thread_id": t["thread_id"],
                         "role": t.get("dimension") or t.get("role") or s["kind"], **f}
                        for s in data["sessions"] for t in s["threads"] for f in t.get("findings") or []]
    data["live"] = None
    _atomic_write(out_path, overview_html(data=data))
    return out_path


def run(harmony: str, focus: Optional[str], out_path: str, build_report: Callable[[str], bytes],
        build_trace: Optional[Callable[[str], Dict[str, Any]]] = None, host: str = "127.0.0.1", port: int = 0,
        interval: float = 10.0, cache_dir: Optional[str] = None, reset_cache: bool = False,
        open_browser: bool = False, write_final_page: bool = True,
        chat_factory: Optional[Callable[[str], Any]] = None, **roots: Any) -> Dict[str, Any]:
    migration = MigrationMonitor(harmony, focus=focus, cache_dir=cache_dir, poll_interval=interval,
                                 reset_cache=reset_cache, **roots)
    print("迁移目录      -> %s" % migration.harmony)
    print("首次读取全部会话(之后每次只读新增内容)…")
    t0 = time.perf_counter()
    migration.start()
    live = sum(1 for s in migration.slots.values() if s["live"])
    print("会话 %d 个(实时 %d、%s %d),首次读取 %.1f 秒" % (
        len(migration.slots), live, UNSUPPORTED, len(migration.slots) - live, time.perf_counter() - t0))
    server = MigrationHTTPServer((host, int(port)), migration, build_report, chat_factory)
    url = "http://%s:%d/" % (host, server.server_address[1])
    print("MigLoop Live  -> %s(会话总览)" % url)
    focus_key = next((k for k, s in migration.slots.items() if focus and os.path.normcase(s["path"]) == os.path.normcase(os.path.abspath(focus))), None)
    if focus_key:
        print("当前会话      -> %ss/%s/" % (url, urllib.parse.quote(focus_key)))
    print("每 %g 秒刷新;Ctrl+C / Ctrl+Break / 关窗口停止,停止时%s最终页面。" % (
        interval, "生成" if write_final_page else "不生成"))
    stopper = Stopper()
    install_stop_signals(stopper)
    if open_browser:
        webbrowser.open(url)
    try:
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            _say("\n正在停止 …")
        finally:
            stopper.stopping.set()
            server.shutdown()
            server.server_close()
            migration.stop()
        if write_final_page:
            _say("生成最终页面(总览 + 各会话完整分析)…")
            path = write_final(migration, out_path, build_report, build_trace)
            _say("最终页面 -> %s" % path)
    finally:
        stopper.done.set()
    return migration.overview()
