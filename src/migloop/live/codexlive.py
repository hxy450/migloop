"""Codex rollout 的增量监控 —— 与 CC 的 ``IncrementalSessionMonitor`` 同协议。

移植自 hmigbot-plus insight/codexlive.py,接到 ``live.monitor.run_live`` 与 CLI 的 ``--live``。

物理介质相同（追加式 JSONL，传输层直接用 ``livestream.TranscriptStream``），
差在两处，这也是本模块的全部内容：

**记录语义。** Codex 的词汇表是 ``response_item``（message / reasoning /
function_call / function_call_output）与 ``event_msg``（task_started /
task_complete / token_count / …），逐条归约进计数器。生命周期是显式事件，
比 CC 靠 stop_hook 推断还干净；token 用量在 ``token_count.info.
total_token_usage`` 里是**累计值**，取最新一条即可，不做加法。

**子代理发现。** CC 的子代理固定在 ``<session_dir>/subagents/``，listdir 即可；
Codex 散落在 ``~/.codex/sessions/YYYY/MM/DD/`` 任意日期目录，靠
``parent_thread_id`` 边 + 同 ``session_id`` 连成树。全量 glob + 逐个读首行
（本机 536 个文件）每 10s 跑一遍不可接受，所以：**首轮**用离线侧现成的
``discover_rollout_tree`` 建树（一次性），**之后**只看 mtime 越过水位线的
新文件，读过首行确认不属于这棵树的路径进负缓存（文件的 session_id 终生不变，
缓存永不失效）。

状态判定是 v1 口径：只认 ``task_started``/``task_complete`` 显式事件。
正在写入的活体 rollout 上事件到达的顺序与粒度还没验过（CC 的活跃判定当年
改了五版才对），拿到活体样本前不做更细的推断。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import deque
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional, Set

from .. import stage_signals
from ..adapters import codex as _codex
from .livestream import TranscriptStream

#: 2:阶段与人工 / 程序下发计数改走 stage_signals.LiveStages,旧 checkpoint 作废重放
CACHE_SCHEMA = "codex-live/4"

#: 计一次工具调用的 response_item 类型(apply_patch 走 custom_tool_call)
_CALL_TYPES = ("function_call", "custom_tool_call")
_OUTPUT_TYPES = ("function_call_output", "custom_tool_call_output")

#: 增量扫描的水位回看余量(秒) —— 文件系统 mtime 粒度与写入延迟的保险。
_WATERMARK_SLACK_S = 60.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _lifecycle(payload_type: str) -> str | None:
    if payload_type == "task_started":
        return "running"
    if payload_type == "task_complete":
        return "completed"
    return None


class CodexLiveMonitor:
    """实现 ``livehub.Monitor`` 协议:start / stop / snapshot / state / cache_path。"""

    def __init__(
        self, jsonl_path: str, cache_dir: str | None = None, poll_interval: float = 30.0,
        reset_cache: bool = False,
    ) -> None:
        self.jsonl_path = os.path.abspath(jsonl_path)
        self.poll_interval = max(0.2, float(poll_interval))
        stem = os.path.splitext(os.path.basename(self.jsonl_path))[0]
        # Codex 文件名是 rollout-<时间戳>-<uuid>.jsonl —— session 身份是尾部
        # uuid,整个 stem 会让「同 session 判定」在 session_meta 读进来之前
        # 全部误判(重放实测:7/12 子代理因此进了负缓存)。
        m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", stem)
        self._sid = m.group(1) if m else stem
        sid = self._sid
        cache_dir = cache_dir or os.path.join(os.path.expanduser("~"), ".migloop", "cache")
        self.cache_path = os.path.join(os.path.abspath(cache_dir), sid + ".codex-live.json")

        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

        self.streams: Dict[str, TranscriptStream] = {}
        self.threads_known: Set[str] = set()
        self.negative: Set[str] = set()
        self.watermark: float = 0.0
        self.events: Deque[Dict[str, Any]] = deque(maxlen=80)
        self._pending_calls: Dict[str, str] = {}
        self.state: Dict[str, Any] = self._fresh_state()

        if reset_cache or not self._load_checkpoint():
            self._bootstrap_tree()

    # ---------- 状态 ----------

    def _fresh_state(self) -> dict[str, Any]:
        return {
            "schema": CACHE_SCHEMA,
            "session_id": self._sid,
            "session_format": "codex",
            "version": 0,
            "records": 0,
            "tool_calls": 0,
            "tool_failures": 0,
            "output_tokens": 0,
            "bytes_read_last": 0,
            "bytes_read_total": 0,
            "status": "waiting",
            "last_update": None,
            "last_error": None,
            "user_prompts": 0,
            "program_prompts": 0,
            "prompt_log": [],
            "started_at": None,
            "ended_at": None,
            "model": None,
            "cwd": None,
            "driver": False,          # exec / MCP 起的会话:输入都是程序下发
            "listed_skills": {},      # 会话注入的 skill 清单(名字 → 路径)
            "modified_skills": [],    # 会话改过文件的 skills/<名字>/ 目录
            "mark_calls": {},         # call_id → 这次调用里的 mark-stage 阶段(等回执确认)
        }

    def _event(self, kind: str, text: str, ts: Any = None) -> None:
        self.events.append({"kind": kind, "text": text, "ts": ts or _now_iso()})

    def _stages(self) -> "stage_signals.LiveStages":
        return stage_signals.LiveStages(self.state, self._event)

    # ---------- 树发现 ----------

    def _bootstrap_tree(self) -> None:
        """首轮:用离线侧的树发现一次性建全 —— 子代理可能早已存在。"""
        rows: list[dict[str, Any]] = []
        try:
            rows = list(_codex.discover_rollout_tree(self.jsonl_path))
        except Exception as exc:
            self._event("error", f"树发现失败,只盯根 rollout: {exc}")
        if not rows:
            rows = [{"path": self.jsonl_path, "meta": {}, "nickname": None}]
        for item in rows:
            self._register(str(item["path"]), dict(item.get("meta") or {}),
                           nickname=item.get("nickname"))
        self.watermark = time.time()

    def _register(self, path: str, meta: dict[str, Any], nickname: Any = None) -> None:
        if path in self.streams:
            return
        kind = "root" if os.path.abspath(path) == self.jsonl_path else "agent"
        stream = TranscriptStream(path=os.path.abspath(path))
        stream.meta = {
            "kind": kind,
            "thread_id": str(meta.get("id") or ""),
            "nickname": str(nickname or "") or None,
            "status": "idle",
            "records": 0,
            "tool_uses": 0,
            "output_tokens": 0,
            "last_ts": None,
        }
        self.streams[stream.path] = stream
        if stream.meta["thread_id"]:
            self.threads_known.add(stream.meta["thread_id"])
        if kind == "agent":
            self._event("agent", f"发现子代理 {nickname or meta.get('id', '')}")

    def _discover_new(self) -> bool:
        """增量:只看 mtime 越过水位线、且不在负缓存里的新文件。"""
        root_dir = None
        try:
            root_dir = _codex._sessions_root(self.jsonl_path)
        except Exception:
            return False
        cutoff = self.watermark - _WATERMARK_SLACK_S
        self.watermark = time.time()
        changed = False
        for dirpath, _dirs, names in os.walk(root_dir):
            for name in names:
                if not name.endswith(".jsonl"):
                    continue
                path = os.path.abspath(os.path.join(dirpath, name))
                if path in self.streams or path in self.negative:
                    continue
                try:
                    if os.path.getmtime(path) < cutoff:
                        continue
                except OSError:
                    continue
                summary = None
                try:
                    summary = _codex.session_summary(path)
                except Exception:
                    summary = None
                if not summary:
                    continue  # 首行还没写完 —— 不进负缓存,下轮再看
                source = summary.get("source") or {}
                spawn = ((source.get("subagent") or {}).get("thread_spawn") or {}) \
                    if isinstance(source, dict) else {}
                root_stream = self.streams.get(self.jsonl_path)
                confirmed = bool(root_stream and root_stream.meta.get("session_id"))
                root_session = (root_stream.meta.get("session_id") if root_stream else None) \
                    or self.state["session_id"]
                same = summary.get("session_id") == root_session
                if same and spawn.get("parent_thread_id") in self.threads_known:
                    self._register(path, summary, nickname=spawn.get("agent_nickname"))
                    changed = True
                elif not same and confirmed:
                    # 别的会话的文件才进负缓存,且 root 身份已确认才算数 ——
                    # 同 session 但父线程还没注册的
                    # **不能拉黑** —— 乱序到达时(深层子代理、bootstrap 从空文件
                    # 起步)孩子常先于父被看到,判死刑就永远丢了;留到下一轮,
                    # 父注册后自然接上。重放实测:12 个子代理被黑掉 7 个。
                    self.negative.add(path)
        return changed

    # ---------- 归约 ----------

    def _process(self, stream: TranscriptStream, rec: dict[str, Any]) -> None:
        m = stream.meta
        m["records"] = int(m.get("records") or 0) + 1
        self.state["records"] += 1
        ts = rec.get("timestamp")
        if ts:
            m["last_ts"] = ts
            m["first_ts"] = m.get("first_ts") or ts
            if self.state.get("started_at") is None or ts < self.state["started_at"]:
                self.state["started_at"] = ts
            if self.state.get("ended_at") is None or ts > self.state["ended_at"]:
                self.state["ended_at"] = ts
        rtype = rec.get("type")
        payload = rec.get("payload") or {}
        ptype = str(payload.get("type") or "")

        if rtype == "session_meta":
            # 身份以**第一条**为准:子代理 rollout 会在后面再嵌一条 root 的
            # session_meta(实测 Lovelace: 先自己的 id,再 root 的),后到的
            # 覆盖会让 12 个 agent 的 thread_id 塌成 3 个。
            if not m.get("thread_id"):
                m["thread_id"] = str(payload.get("id") or "")
            if not m.get("session_id"):
                m["session_id"] = payload.get("session_id") or payload.get("id")
                if m.get("kind") == "root":
                    self.state["driver"] = _codex._driver_session(payload)
                    m["cwd"] = payload.get("cwd")
                    self.state["cwd"] = payload.get("cwd")
            if m["thread_id"]:
                self.threads_known.add(m["thread_id"])
            return
        if m.get("kind") == "root":
            self._root_stage(stream, rtype, payload, ts)
        elif not m.get("activated") and (
                _codex._own_settings(rec, str(m.get("thread_id") or ""))
                or (rtype == "response_item" and ptype == "message" and payload.get("role") == "developer"
                    and _codex._FORK_MARKER in _codex._content_text(payload.get("content")))):
            # fork 子会话:到这里为止是抄来的父会话前缀 —— 之前记的工具与用量作废
            m["activated"] = True
            m["tool_uses"] = m["tool_uses_outer"] = 0
            m["_inherited"] = list(m.get("_totals") or [0, 0, 0])

        if rtype == "response_item":
            if ptype in _CALL_TYPES:
                # 与离线同口径:code 模式 exec 按里层算,外层另记;主会话与子会话分开
                raw = payload.get("arguments") if ptype == "function_call" else payload.get("input")
                raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                inner = _codex._call_tool_count({"name": payload.get("name"), "ptype": ptype, "raw": raw})
                m["tool_uses"] = int(m.get("tool_uses") or 0) + inner
                m["tool_uses_outer"] = int(m.get("tool_uses_outer") or 0) + 1
                if m.get("kind") == "root":
                    self.state["tool_calls"] += inner
                    spawns = 1 if payload.get("name") == "spawn_agent" else (
                        len(re.findall(r"\btools\.spawn_agent\s*\(", raw)) if payload.get("name") == "exec" else 0)
                    self.state["agent_dispatches"] = int(self.state.get("agent_dispatches") or 0) + spawns
                call_id = str(payload.get("call_id") or "")
                if call_id:
                    self._pending_calls[call_id] = str(payload.get("name") or "")
            elif ptype in _OUTPUT_TYPES:
                self._pending_calls.pop(str(payload.get("call_id") or ""), None)
                failed = False
                try:
                    failed = bool(_codex._tool_failed(payload.get("output")))
                except Exception:
                    failed = False
                if failed:
                    self.state["tool_failures"] += 1
            return

        if rtype == "event_msg":
            status = _lifecycle(ptype)
            if status:
                m["status"] = status
                if ptype == "task_complete" and m.get("kind") == "agent":
                    self._event("agent", f"子代理完成 {m.get('nickname') or m.get('thread_id')}")
            elif ptype == "token_count":
                usage = (payload.get("info") or {}).get("total_token_usage") or {}
                # 累计值,取最新 —— 不做加法;累计值变了算一次请求
                totals = [int(usage.get(k) or 0) for k in ("input_tokens", "cached_input_tokens", "output_tokens")]
                if totals != m.get("_totals"):
                    m["requests"] = int(m.get("requests") or 0) + 1
                    m["_totals"] = totals
                base = m.get("_inherited") or [0, 0, 0]
                m["input_tokens"], m["cached_tokens"], m["output_tokens"] = [max(0, a - b) for a, b in zip(totals, base)]

    def _root_stage(self, stream: TranscriptStream, rtype: Any, payload: dict[str, Any], ts: Any) -> None:
        """主线记录 → 阶段信号与人工 / 程序下发计数(与离线 codex 同一套翻译)。"""
        stages = self._stages()
        ptype = payload.get("type")
        cwd = stream.meta.get("cwd")
        if rtype == "turn_context" and payload.get("model"):
            self.state["model"] = payload.get("model")
        if rtype == "response_item" and ptype == "message" and payload.get("role") in ("user", "developer"):
            content = payload.get("content")
            for item in content if isinstance(content, list) else [content]:
                text = item.get("text") if isinstance(item, dict) else item
                if isinstance(text, str) and "(file:" in text:
                    for name, where in _codex._SKILL_LIST_ENTRY.findall(text):
                        self.state["listed_skills"].setdefault(name, where.strip())
            if payload.get("role") == "user":
                parts = _codex._user_message_parts(content)
                mention = False
                for kind, text in parts:
                    hit = _codex._SKILL_INJECT.match(text) or (
                        _codex._SKILL_MENTION.match(text) if kind == "human" else None)
                    stage = stage_signals.normalize(hit.group(1)) if hit else None
                    if stage:
                        mention = True
                        stages.signal(stage, ts)
                kinds = {kind for kind, _ in parts} - {"injected"}
                if kinds:
                    kind = "human" if "human" in kinds else "program"
                    self._prompt(kind, " ".join(t for k, t in parts if k == kind), ts, command=mention)
        elif rtype == "event_msg" and ptype == "user_message" and str(payload.get("message") or "").strip():
            self._prompt("human", str(payload.get("message")), ts, command=False)
        elif rtype == "response_item" and ptype in _CALL_TYPES:
            raw = payload.get("arguments") if ptype == "function_call" else payload.get("input")
            raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            call = {"name": payload.get("name"), "raw": raw}
            for patch in _codex._extract_apply_patches(raw):
                for row in _codex._patch_entries(patch, cwd):
                    for hit in _codex._SKILL_DIR.finditer(str(row.get("brief") or "")):
                        if hit.group(1).lower() not in self.state["modified_skills"]:
                            self.state["modified_skills"].append(hit.group(1).lower())
            stage = _codex._call_skill_stage(call, self.state["listed_skills"],
                                             set(self.state["modified_skills"]), cwd)
            if stage:
                stages.signal(stage, ts)
            marked = stage_signals.mark_calls(raw)
            if marked and payload.get("call_id"):
                self.state["mark_calls"][str(payload["call_id"])] = [marked, ts]
        elif rtype == "response_item" and ptype in _OUTPUT_TYPES:
            pending = self.state["mark_calls"].pop(str(payload.get("call_id") or ""), None)
            if pending:
                output = _codex._content_text(payload.get("output"))
                if stage_signals.mark_ran(not _codex._tool_failed(output), output):
                    for marked in pending[0]:
                        stages.mark(marked, pending[1])
        if ts:
            stages.confirm(ts)

    def _prompt(self, kind: str, text: str, ts: Any, command: bool) -> None:
        if self.state.get("driver"):
            kind = "program"
        key = "user_prompts" if kind == "human" else "program_prompts"
        self.state[key] = int(self.state.get(key) or 0) + 1
        from .monitor import _log_prompt
        _log_prompt(self.state, ts, kind, text)
        self._event("prompt", "%s: %s" % ("用户输入" if kind == "human" else "程序下发", " ".join(text.split())[:100]), ts)
        if kind == "human":
            self._stages().human(text, ts, command=command)

    def _overall_status(self) -> str:
        root = self.streams.get(self.jsonl_path)
        if root and root.meta.get("status") == "running":
            return "running"
        if any(s.meta.get("status") == "running" for s in self.streams.values()):
            return "running"
        if root and root.meta.get("status") == "completed":
            return "waiting"
        return "waiting"

    # ---------- 轮询 ----------

    def poll_once(self) -> bool:
        with self.lock:
            self.state["bytes_read_last"] = 0
            changed = self._discover_new()
            for stream in list(self.streams.values()):
                records, nbytes, reset = stream.read_new()
                if reset:
                    self._reset_for_replay()
                    return self.poll_once()
                if nbytes:
                    changed = True
                    self.state["bytes_read_last"] += nbytes
                    self.state["bytes_read_total"] += nbytes
                for rec in records:
                    self._process(stream, rec)
            if changed:
                self.state["status"] = self._overall_status()
                self.state["version"] += 1
                self.state["last_update"] = _now_iso()
                self.state["last_error"] = None
        if changed:
            self.save_checkpoint()
        return changed

    def _reset_for_replay(self) -> None:
        self._event("reset", "检测到 rollout 截断/替换，重新建立增量状态")
        self.streams.clear()
        self.threads_known.clear()
        self.negative.clear()
        self._pending_calls.clear()
        self.state = self._fresh_state()
        self._bootstrap_tree()

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # 保留上一版状态,把错误亮出来
                with self.lock:
                    self.state["last_error"] = f"{type(exc).__name__}: {exc}"
                    self.state["version"] += 1
                self._event("error", self.state["last_error"])
            self.stop_event.wait(self.poll_interval)

    def start(self) -> None:
        self.poll_once()
        self.thread = threading.Thread(target=self._loop, name="migloop-codex-live", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)
        self.save_checkpoint()

    # ---------- 对外 ----------

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            agents = []
            total_out = total_in = total_cached = total_req = 0
            for stream in self.streams.values():
                m = stream.meta
                total_out += int(m.get("output_tokens") or 0)
                total_in += max(0, int(m.get("input_tokens") or 0) - int(m.get("cached_tokens") or 0))
                total_cached += int(m.get("cached_tokens") or 0)
                total_req += int(m.get("requests") or 0)
                if m.get("kind") != "agent":
                    continue
                agents.append({
                    "agent_id": m.get("thread_id"),
                    "desc": m.get("nickname") or m.get("thread_id"),
                    "status": m.get("status"),
                    "tool_uses": m.get("tool_uses", 0),
                    "output_tokens": m.get("output_tokens", 0),
                    "last_ts": m.get("last_ts"),
                })
            agents.sort(key=lambda x: (x.get("status") != "running", str(x.get("desc") or "")))
            out = dict(self.state)
            out["output_tokens"] = total_out
            out["subagent_tool_calls"] = sum(int(s.meta.get("tool_uses") or 0) for s in self.streams.values()
                                             if s.meta.get("kind") == "agent")
            out["tool_calls_outer"] = sum(int(s.meta.get("tool_uses_outer") or 0) for s in self.streams.values()
                                          if s.meta.get("kind") == "root")
            out["input_tokens"] = total_in
            out["cache_read_tokens"] = total_cached
            out["requests"] = total_req
            # live 面板(live.monitor.LIVE_HTML)与 CC 共用;codex 没有的字段给中性值
            out.setdefault("current_stage", stage_signals.SESSION)
            out.setdefault("write_files", 0)
            out["agents"] = agents
            out["agent_counts"] = {
                k: sum(1 for a in agents if a["status"] == k)
                for k in ("running", "completed", "idle")
            }
            out["events"] = list(self.events)
            out["cache_path"] = self.cache_path
            out["source_bytes"] = sum(
                os.path.getsize(p) if os.path.isfile(p) else 0 for p in self.streams
            )
            return out

    # ---------- checkpoint ----------

    def save_checkpoint(self) -> None:
        with self.lock:
            payload = {
                "schema": CACHE_SCHEMA,
                "source_file": self.jsonl_path,
                "saved_at": _now_iso(),
                "watermark": self.watermark,
                "state": self.state,
                "streams": [s.to_json() for s in self.streams.values()],
                "threads_known": sorted(self.threads_known),
                "negative": sorted(self.negative),
            }
        with suppress(OSError):
            _atomic_write(self.cache_path,
                          json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    def _load_checkpoint(self) -> bool:
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        if data.get("schema") != CACHE_SCHEMA or data.get("source_file") != self.jsonl_path:
            return False
        try:
            self.state = dict(data["state"])
            self.watermark = float(data.get("watermark") or 0.0)
            self.threads_known = set(data.get("threads_known") or [])
            self.negative = set(data.get("negative") or [])
            for row in data.get("streams") or []:
                stream = TranscriptStream.from_json(row)
                self.streams[stream.path] = stream
        except (KeyError, TypeError, ValueError):
            return False
        self._event("resume", "从 checkpoint 恢复增量状态")
        return True
