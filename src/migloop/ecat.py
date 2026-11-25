"""ECAT 会话适配 —— 把精修 run 的 generator / discriminator 会话接进报告。

移植自 hmigbot-plus 的 insight/ecat.py(90b6726d、739088ca、72c56b60、3fd7850d),只保留解析与
审计;产品侧的项目空间准入换成「rollout 的 cwd 落在鸿蒙工程目录里」。

ECAT 给每个角色一个独立的 CLAUDE_CONFIG_DIR(``<harmony>/.ecat/agents/<role>``),
Claude Code 把 transcript 落在 ``<config_dir>/projects/<slug(cwd)>/<sid>.jsonl``,
格式与主迁移会话完全相同,``adapters.claude`` 原样能解析。本模块只管三件
源特有的事:根在哪、一个会话属于哪个角色哪一轮、一次 run 里各轮会话怎么挂到
熵曲线上。渲染层不认识 ECAT,一律吃统一 trace(分层契约见 adapters/base.py)。

codex_sdk 线没有这层目录约定:Codex 不读 CLAUDE_CONFIG_DIR,角色 rollout 一律落
``~/.codex/sessions/<日期>/rollout-…-<thread_id>.jsonl``,路径里没有角色也没有工程。
关联靠 ECAT runner 自己留的记录:每个角色的事件流 tee 在
``<runs_dir>/<iteration>/<role>.stream.jsonl``,首行 init 的 ``session_id`` 就是
Codex thread id。角色与轮次直接来自路径,不再解析提示词;generator 跨轮 resume
同一 thread 时,一个 rollout 挂到多个轮次。

读盘纪律:正在报告的那份 transcript 不再整份重读 —— 角色、起止、判官派发都从已解析的
trace 取,轮次只看开工提示所在的文件头;同工程其它 ECAT 会话的单趟扫描按 (mtime, size)
记住,文件不变不重扫。
"""

from __future__ import annotations

import glob
import json
import os
import re
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from . import adapters
from .cc_records import is_request_replay

ROLES: tuple[str, ...] = ("generator", "discriminator")

_T = TypeVar("_T")

#: shared_scan() 期间的扫描结果;平时为 None,每次调用照常现读
_SCAN: ContextVar[dict[tuple[str, str], Any] | None] = ContextVar("migloop_ecat_scan", default=None)


@contextmanager
def shared_scan() -> Iterator[None]:
    """块内同一工程的 transcript / run 目录只扫一遍。

    一份会话总览要 extract 几十个会话,每个 ECAT 会话都会回头要 run 上下文;不共享就是
    会话数 × run 数遍的目录扫描。只用于一次性的只读归约 —— 块内新落盘的东西看不见。
    """
    token = _SCAN.set({})
    try:
        yield
    finally:
        _SCAN.reset(token)


def _scanned(kind: str, harmony: str | Path | None, scan: Callable[[], _T]) -> _T:
    cache = _SCAN.get()
    if cache is None:
        return scan()
    key = (kind, str(harmony or ""))
    if key not in cache:
        cache[key] = scan()
    result: _T = cache[key]
    return result


_ROLE_RE = re.compile(r"[\\/]\.ecat[\\/]agents[\\/](generator|discriminator)[\\/]projects[\\/]")
# 两个角色的开工提示都带这句(gradient/builder.py 与 loop 的提示模板)
_ITER_RE = re.compile(r"ECAT adversarial loop \(iteration (\d+)\)")
# 判官派发的 description 固定以 "Judge <dimension> dimension" 开头
_JUDGE_PREFIX = "judge"
# 判官开工提示的固定句式(plugins/ecat 的判官模板);判官流文件每轮覆盖,
# 早先轮次的判官只剩这一处能认出维度
_JUDGE_DIM_RE = re.compile(r"evaluator for the \*\*(\w+)\*\* dimension")
_JUDGE_SCAN_BYTES = 262144
_LOOP_ROLE_RE = re.compile(r"You are the (Generator|Discriminator) in the ECAT adversarial loop")


def ecat_roots(harmony: str | Path | None) -> list[Path]:
    """ECAT 各角色的 CLAUDE_CONFIG_DIR(只返回已经有 projects/ 的)。"""
    if not harmony:
        return []
    base = Path(harmony) / ".ecat" / "agents"
    return [base / role for role in ROLES if (base / role / "projects").is_dir()]


def role_of(path: str | Path) -> str | None:
    """这份 transcript 是哪个角色的;不是 ECAT 会话返回 None。

    CC 线看路径落在哪个角色的根下;codex rollout 路径里没有角色,按 thread id
    到它 cwd 工程的 run 目录里反查(见 codex_binding)。"""
    m = _ROLE_RE.search(str(path))
    if m:
        return m.group(1)
    bind = codex_binding(path)
    return str(bind["role"]) if bind else None


def harmony_of(path: str | Path) -> str | None:
    """从 ECAT transcript 反推鸿蒙工程目录:CC 线是 ``.ecat`` 的上一级,
    codex 线是 rollout 的 cwd(反查时已核对过它就是记着这个 thread 的工程)。"""
    if _ROLE_RE.search(str(path)):
        parts = Path(path).resolve().parts
        with suppress(ValueError):
            return str(Path(*parts[: parts.index(".ecat")]))
        return None
    bind = codex_binding(path)
    return str(bind["harmony"]) if bind else None


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    with suppress(ValueError):
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return None


def _prompt_text(rec: dict[str, Any]) -> str:
    msg = rec.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


#: path -> ((mtime, size), 单趟扫描结果);同工程的 ECAT 会话在多个视图里反复要
_META_CACHE: dict[str, tuple[tuple[float, int], dict[str, Any]]] = {}
_META_CACHE_MAX = 1024


def _stat_sig(path: str) -> tuple[float, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime, st.st_size)


def _remember(path: str, sig: tuple[float, int] | None, meta: dict[str, Any]) -> None:
    if sig is None:
        return
    if len(_META_CACHE) >= _META_CACHE_MAX:
        _META_CACHE.pop(next(iter(_META_CACHE)))
    _META_CACHE[path] = (sig, meta)


def _subagent_count(path: str, sid: str) -> int:
    return len(glob.glob(os.path.join(os.path.dirname(path), sid, "subagents", "*.jsonl")))


def _cc_meta(path: str, role: str, iteration: int | None, first: datetime | None,
             last: datetime | None, judge: dict[str, int]) -> dict[str, Any]:
    sid = os.path.basename(path).split(".")[0]
    return {
        "role": role,
        "iteration": iteration,
        "session_id": sid,
        "sid8": sid[:8],
        "transcript": path,
        "started_at": first.isoformat() if first else None,
        "ended_at": last.isoformat() if last else None,
        "duration_ms": int((last - first).total_seconds() * 1000) if first and last else None,
        "subagents": _subagent_count(path, sid),
        "judge_dispatch": judge,
    }


def session_meta(path: str, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    """一份 ECAT transcript 的角色、轮次、起止、子代理数、判官派发形态。

    ``judge_dispatch`` 按 subagent_type 计数 —— 正常 run 只有 entropy-judge;
    出现 general-purpose 说明判官 agent 没种下、模型自行退化重派(#161)。

    给了 ``trace``(这份 transcript 已经解析过)就从 trace 取,只读文件头认轮次;
    没给时单趟扫一遍并按 (mtime, size) 记住。

    codex rollout 走 codex_binding:轮次、起止都来自 run 目录里的 stream,
    判官是 runner 另起的会话而不是子代理派发,``judge_dispatch`` 恒为空。
    """
    m = _ROLE_RE.search(str(path))
    if not m:
        bind = codex_binding(path)
        return _codex_session_meta(path, bind, trace) if bind else {}
    path = str(path)
    key = os.path.normcase(os.path.abspath(path))
    sig = _stat_sig(path)
    hit = _META_CACHE.get(key)
    if hit is not None and hit[0] == sig:
        return {**hit[1], "transcript": path}
    role = m.group(1)
    if trace is not None:
        info = _meta_from_trace(path, role, trace)
    else:
        info = _scan_meta(path, role)
    _remember(key, sig, info)
    return dict(info)


def _head_iteration(path: str) -> int | None:
    """开工提示里的轮次。提示是第一条 user 记录,只读文件头,不整份重读。"""
    with suppress(OSError), open(path, encoding="utf-8", errors="replace") as fh:
        m = _ITER_RE.search(fh.read(_JUDGE_SCAN_BYTES))
        return int(m.group(1)) if m else None
    return None


def _meta_from_trace(path: str, role: str, trace: dict[str, Any]) -> dict[str, Any]:
    meta = trace.get("meta") or {}
    judge: dict[str, int] = {}
    for t in trace.get("tools") or []:
        if t.get("name") not in ("Agent", "Task"):
            continue
        if str(t.get("agent_desc") or "").lower().startswith(_JUDGE_PREFIX):
            kind = str(t.get("agent_type") or "?")
            judge[kind] = judge.get(kind, 0) + 1
    return _cc_meta(path, role, _head_iteration(path), _parse_ts(meta.get("started_at")),
                    _parse_ts(meta.get("ended_at")), judge)


def _scan_meta(path: str, role: str) -> dict[str, Any]:
    iteration: int | None = None
    first: datetime | None = None
    last: datetime | None = None
    judge: dict[str, int] = {}
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or is_request_replay(rec):
                continue
            ts = _parse_ts(rec.get("timestamp"))
            if ts is not None:
                first = ts if first is None or ts < first else first
                last = ts if last is None or ts > last else last
            if rec.get("type") == "user" and iteration is None:
                mi = _ITER_RE.search(_prompt_text(rec))
                if mi:
                    iteration = int(mi.group(1))
            if rec.get("type") == "assistant":
                for tool_type, inp in _tool_uses(rec):
                    if tool_type not in ("Agent", "Task"):
                        continue
                    if str(inp.get("description", "")).lower().startswith(_JUDGE_PREFIX):
                        kind = str(inp.get("subagent_type") or "?")
                        judge[kind] = judge.get(kind, 0) + 1
    return _cc_meta(path, role, iteration, first, last, judge)


def _tool_uses(rec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    msg = rec.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, list):
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for blk in content:
        if isinstance(blk, dict) and blk.get("type") == "tool_use":
            inp = blk.get("input")
            out.append((str(blk.get("name") or ""), inp if isinstance(inp, dict) else {}))
    return out


def iter_transcripts(harmony: str | Path | None) -> list[str]:
    return _scanned("transcripts", harmony, lambda: _iter_transcripts(harmony))


def _iter_transcripts(harmony: str | Path | None) -> list[str]:
    """harmony 下所有 ECAT 主会话 transcript(不含 subagents/ 里的)。"""
    paths: list[str] = []
    for root in ecat_roots(harmony):
        paths.extend(glob.glob(os.path.join(str(root), "projects", "*", "*.jsonl")))
    return sorted(paths)


# ── codex 线:按 run 目录里的 stream 反查 rollout ──────────────────────────

_ROLLOUT_RE = re.compile(
    r"^rollout-.*-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.jsonl$", re.IGNORECASE)


def _rollout_tid(path: str | Path) -> str | None:
    m = _ROLLOUT_RE.match(os.path.basename(str(path)))
    return m.group(1).lower() if m else None


def _codex_root() -> str:
    cx: Any = adapters.get("codex")
    return str(cx.default_root())


def _stream_meta(path: Path) -> dict[str, Any] | None:
    """一份 ``<role>.stream.jsonl`` 的 thread id 与本轮起止;首条不是 init 的不认。"""
    tid = ""
    first: datetime | None = None
    last: datetime | None = None
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if not tid:
                if rec.get("subtype") != "init" or not rec.get("session_id"):
                    return None
                tid = str(rec["session_id"]).lower()
            ts = _parse_ts(rec.get("timestamp"))
            if ts is not None:
                first = ts if first is None or ts < first else first
                last = ts if last is None or ts > last else last
    if not tid:
        return None
    return {"thread_id": tid, "started_at": first, "ended_at": last}


def _stream_bindings(runs_dir: Path) -> list[dict[str, Any]]:
    """``<runs_dir>/<N>/<role>.stream.jsonl`` → 每份一条 {role, iteration, thread_id, 起止}。

    CC 线的 run 目录也有这些 stream(id 是 CC 的 session id),但 codex 根下找不到
    同名 rollout,后面自然落空;两条线不必在这里分流。"""
    out: list[dict[str, Any]] = []
    with suppress(OSError):
        it_dirs = sorted((p for p in runs_dir.iterdir() if p.is_dir() and p.name.isdigit()),
                         key=lambda p: int(p.name))
        for it_dir in it_dirs:
            for role in ROLES:
                f = it_dir / f"{role}.stream.jsonl"
                if not f.is_file():
                    continue
                with suppress(OSError):
                    meta = _stream_meta(f)
                    if meta:
                        out.append({"role": role, "iteration": int(it_dir.name),
                                    "stream": str(f), **meta})
    return out


class _CodexRollouts:
    """codex 根下的 rollout 索引:文件名给 thread id(免读),首行按需读、读过就记。

    一次 list_runs 只建一份 —— 逐个 thread 去 glob 整个根,几个角色乘几轮就是
    十几遍全盘扫描。"""

    def __init__(self) -> None:
        self._paths: dict[str, str] = {}
        with suppress(OSError):
            for hit in glob.iglob(os.path.join(_codex_root(), "**", "*.jsonl"), recursive=True):
                tid = _rollout_tid(hit)
                if tid and os.path.isfile(hit):
                    self._paths.setdefault(tid, hit)
        self._summary: dict[str, dict[str, Any]] = {}
        self._children: dict[str, int] | None = None

    def path(self, tid: str) -> str | None:
        return self._paths.get(tid.lower())

    def summary(self, tid: str) -> dict[str, Any]:
        tid = tid.lower()
        if tid not in self._summary:
            path = self._paths.get(tid)
            cx: Any = adapters.get("codex")
            self._summary[tid] = (cx.session_summary(path) if path else None) or {}
        return self._summary[tid]

    def subagents(self, tid: str) -> int:
        """并行 worker 是共用 root session_id 的子 rollout(adapters.codex 的约定)。
        要数它们得读遍全根的首行,只在真有 codex ECAT 会话时做一次。"""
        if self._children is None:
            self._children = {}
            for other in self._paths:
                s = self.summary(other)
                root = str(s.get("session_id") or "").lower()
                if root and root != str(s.get("id") or "").lower():
                    self._children[root] = self._children.get(root, 0) + 1
        return self._children.get(tid.lower(), 0)


def _norm_dir(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def _admits(harmony: str | Path, cwd: str) -> bool:
    """rollout 的 cwd 得落在这个工程目录里 —— stream 里记了 thread id 不等于是本工程的会话。"""
    if not cwd:
        return False
    root, real = _norm_dir(str(harmony)), _norm_dir(cwd)
    with suppress(ValueError):
        return os.path.commonpath([real, root]) == root
    return False


def _codex_sessions(
    harmony: str | Path, bindings: list[dict[str, Any]], index: _CodexRollouts,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in bindings:
        tid = str(b["thread_id"])
        path = index.path(tid)
        if not path or not _admits(harmony, str(index.summary(tid).get("cwd") or "")):
            continue
        first: datetime | None = b.get("started_at")
        last: datetime | None = b.get("ended_at")
        out.append({
            "role": b["role"],
            "iteration": b["iteration"],
            "session_id": tid,
            # codex 的 thread id 是时间序 uuid,前 8 位整天都一样;会话列表对 codex
            # 行显示的也是末 8 位
            "sid8": tid[-8:],
            "transcript": path,
            "started_at": first.isoformat() if first else None,
            "ended_at": last.isoformat() if last else None,
            "duration_ms": int((last - first).total_seconds() * 1000) if first and last else None,
            "subagents": index.subagents(tid),
            "judge_dispatch": {},
            "format": "codex",
        })
    return out


def codex_binding(path: str | Path) -> dict[str, Any] | None:
    """codex rollout → 它在哪个工程的哪次 run 里扮演什么角色(可能多轮)。

    工程取 rollout 的 cwd,再到 ``<cwd>/.migbot/ecat_runs`` 各 run 的 stream 里按
    thread id 找;不是 rollout、cwd 里没有 run、或没有 stream 记着它,都返回 None。
    只碰 run 目录里那几份 generator / discriminator stream,便宜到可以每次现算。"""
    tid = _rollout_tid(path)
    if not tid:
        return None
    cx: Any = adapters.get("codex")
    cwd = str((cx.session_summary(str(path)) or {}).get("cwd") or "")
    base = Path(cwd) / ".migbot" / "ecat_runs" if cwd else None
    if base is None or not base.is_dir():
        return None
    for d in sorted(p for p in base.glob("run_*") if p.is_dir()):
        hits = [b for b in _stream_bindings(d) if b["thread_id"] == tid]
        if hits:
            return {
                "harmony": cwd,
                "run_id": d.name,
                "runs_dir": str(d),
                "role": hits[0]["role"],
                "iterations": sorted({int(b["iteration"]) for b in hits}),
                "started_at": min((b["started_at"] for b in hits if b["started_at"]), default=None),
                "ended_at": max((b["ended_at"] for b in hits if b["ended_at"]), default=None),
            }
    return None


def _codex_session_meta(path: str | Path, bind: dict[str, Any],
                        trace: dict[str, Any] | None = None) -> dict[str, Any]:
    tid = str(_rollout_tid(path))
    first: datetime | None = bind.get("started_at")
    last: datetime | None = bind.get("ended_at")
    # 已解析的 trace 里子 rollout 就是 agents;没有 trace 时才去读全根的首行
    subagents = (len(trace.get("agents") or []) if trace is not None
                 else _CodexRollouts().subagents(tid))
    return {
        "role": bind["role"],
        "iteration": bind["iterations"][0] if bind["iterations"] else None,
        "iterations": list(bind["iterations"]),
        "session_id": tid,
        "sid8": tid[-8:],
        "transcript": str(path),
        "started_at": first.isoformat() if first else None,
        "ended_at": last.isoformat() if last else None,
        "duration_ms": int((last - first).total_seconds() * 1000) if first and last else None,
        "subagents": subagents,
        "judge_dispatch": {},
        "format": "codex",
    }


def codex_roles(harmony: str | Path | None) -> dict[str, str]:
    """本工程 run 目录里记过的 codex thread id → 角色(会话列表打角色徽标用)。"""
    if not harmony:
        return {}
    base = Path(harmony) / ".migbot" / "ecat_runs"
    if not base.is_dir():
        return {}
    out: dict[str, str] = {}
    for d in sorted(p for p in base.glob("run_*") if p.is_dir()):
        for b in _stream_bindings(d):
            out.setdefault(str(b["thread_id"]), str(b["role"]))
    return out


def stream_sessions(harmony: str | Path | None) -> dict[str, list[dict[str, Any]]]:
    return _scanned("streams", harmony, lambda: _stream_sessions(harmony))


def _stream_sessions(harmony: str | Path | None) -> dict[str, list[dict[str, Any]]]:
    """运行时会话 id → 它在各 run 里担的角色(``run_id`` / ``role`` / ``iteration`` / ``dimension``)。

    generator 跨轮复用同一个会话,所以值是列表。判官流在 ``transcripts/`` 下、每轮
    覆盖,只查得到末轮,``iteration`` 为 None。
    """
    out: dict[str, list[dict[str, Any]]] = {}
    if not harmony:
        return out
    base = Path(harmony) / ".migbot" / "ecat_runs"
    for stream in sorted(base.glob("run_*/*/*.stream.jsonl")):
        slot, name = stream.parent.name, stream.name.split(".")[0]
        if slot.isdigit() and name in ROLES:
            entry: dict[str, Any] = {"role": name, "iteration": int(slot), "dimension": None}
        elif slot == "transcripts" and name.startswith("judge_"):
            entry = {"role": "judge", "iteration": None, "dimension": name[len("judge_"):]}
        else:
            continue
        first: Any = None
        with suppress(OSError, json.JSONDecodeError), stream.open(encoding="utf-8", errors="replace") as fh:
            first = json.loads(fh.readline() or "null")
        tid = str(first.get("session_id") or "") if isinstance(first, dict) else ""
        if tid and first.get("subtype") == "init":
            out.setdefault(tid, []).append({"run_id": stream.parent.parent.name, **entry})
    return out


def loop_role(path: str | Path) -> str | None:
    """从开工提示认出 generator / discriminator;都不是返回 None。

    DevEco 线的角色流不记运行时会话 id(2026-11-12 实测 ``sessionId`` 为空串),
    ``stream_sessions`` 查不到,只剩提示词这一处事实。
    """
    with suppress(OSError), open(path, encoding="utf-8", errors="replace") as fh:
        m = _LOOP_ROLE_RE.search(fh.read(_JUDGE_SCAN_BYTES))
        return m.group(1).lower() if m else None
    return None


def judge_dimension(path: str | Path) -> str | None:
    """从开工提示认出判官维度;不是判官会话返回 None。两种 transcript 格式通用。"""
    with suppress(OSError), open(path, encoding="utf-8", errors="replace") as fh:
        m = _JUDGE_DIM_RE.search(fh.read(_JUDGE_SCAN_BYTES))
        return m.group(1) if m else None
    return None


def _load_history(runs_dir: Path) -> list[dict[str, Any]]:
    """entropy_history.jsonl → 按轮次去重(终评会把末轮再记一次,取末条的 H,
    保留首条的时间戳当该轮起点)。"""
    by_iter: dict[int, dict[str, Any]] = {}
    hist = runs_dir / "entropy_history.jsonl"
    if not hist.is_file():
        return []
    for line in hist.read_text(encoding="utf-8", errors="replace").splitlines():
        with suppress(json.JSONDecodeError, TypeError, ValueError, KeyError):
            rec = json.loads(line)
            it = int(rec["iteration"])
            hard, soft = _split_details(rec.get("details"))
            row = by_iter.get(it)
            if row is None:
                by_iter[it] = {
                    "iteration": it,
                    "total_H": rec.get("total_H"),
                    "breakdown": rec.get("breakdown") or {},
                    "hard_issues": hard,
                    "soft_scores": soft,
                    "started_at": rec.get("timestamp"),
                }
            else:
                row["total_H"] = rec.get("total_H")
                row["breakdown"] = rec.get("breakdown") or {}
                if hard or soft:
                    row["hard_issues"], row["soft_scores"] = hard, soft
    return [by_iter[k] for k in sorted(by_iter)]


def _split_details(details: Any) -> tuple[dict[str, list[str]], dict[str, float]]:
    """entropy_history 的 details → 每维硬检查问题列表 + 判官软分。

    硬检查问题取 ``issues`` / ``fails``(非空才记);软分取 ``agentic_verdict.score``。
    两者并列才能看出「硬检查报问题、判官给 0 分」这种口径打架。
    """
    hard: dict[str, list[str]] = {}
    soft: dict[str, float] = {}
    if not isinstance(details, dict):
        return hard, soft
    for dim, d in details.items():
        if not isinstance(d, dict):
            continue
        issues = [str(x) for k in ("issues", "fails") for x in (d.get(k) or []) if x]
        if issues:
            hard[str(dim)] = issues
        verdict = d.get("agentic_verdict")
        if isinstance(verdict, dict) and isinstance(verdict.get("score"), (int, float)):
            soft[str(dim)] = float(verdict["score"])
    return hard, soft


def list_runs(harmony: str | Path | None) -> list[dict[str, Any]]:
    return _scanned("runs", harmony, lambda: _list_runs(harmony))


def _list_runs(harmony: str | Path | None) -> list[dict[str, Any]]:
    """``<harmony>/.migbot/ecat_runs/run_*`` 逐个聚合,最新的在前。

    CC 线会话归属 run 的规则:按开工时间落在 [本 run 首条熵记录, 下一 run 首条
    熵记录)之内;归属轮次看提示里的 ``iteration N``。不靠文件 mtime —— 会话可能
    被事后拷贝/触碰。codex 线 run 目录自己记着每轮各角色的 thread id,直接按它
    挂,不用猜;同一 thread 跨轮复用时每轮各挂一条。
    """
    if not harmony:
        return []
    base = Path(harmony) / ".migbot" / "ecat_runs"
    if not base.is_dir():
        return []
    sessions = [session_meta(p) for p in iter_transcripts(harmony)]
    sessions.sort(key=lambda s: s.get("started_at") or "")

    runs: list[dict[str, Any]] = []
    for d in sorted(p for p in base.glob("run_*") if p.is_dir()):
        hist = _load_history(d)
        first_ts = _parse_ts(hist[0].get("started_at")) if hist else None
        runs.append({"run_id": d.name, "runs_dir": str(d), "_start": first_ts, "_hist": hist,
                     "_bind": _stream_bindings(d)})
    index = _CodexRollouts() if any(r["_bind"] for r in runs) else None

    out: list[dict[str, Any]] = []
    for i, run in enumerate(runs):
        start: datetime | None = run["_start"]
        nxt: datetime | None = runs[i + 1]["_start"] if i + 1 < len(runs) else None
        mine = [
            s for s in sessions
            if start is not None
            and (st := _parse_ts(s.get("started_at"))) is not None
            and st >= start
            and (nxt is None or st < nxt)
        ]
        if index is not None:
            mine.extend(_codex_sessions(harmony, run["_bind"], index))
            mine.sort(key=lambda s: s.get("started_at") or "")
        history: list[dict[str, Any]] = run["_hist"]
        iterations: list[dict[str, Any]] = []
        prev_h: float | None = None
        for row in history:
            h = row.get("total_H")
            h_val = float(h) if isinstance(h, (int, float)) else None
            iterations.append({
                "iteration": row["iteration"],
                "total_H": h_val,
                "delta_H": (h_val - prev_h) if h_val is not None and prev_h is not None else None,
                "breakdown": row["breakdown"],
                "hard_issues": row.get("hard_issues") or {},
                "soft_scores": row.get("soft_scores") or {},
                "started_at": row["started_at"],
                "sessions": [
                    _public(s) for s in mine if s.get("iteration") == row["iteration"]
                ],
            })
            prev_h = h_val if h_val is not None else prev_h
        known = {it["iteration"] for it in iterations}
        unmatched = [_public(s) for s in mine if s.get("iteration") not in known]
        ends = [e for e in (_parse_ts(s.get("ended_at")) for s in mine) if e is not None]
        ends.extend(t for t in (_parse_ts(r.get("started_at")) for r in history) if t is not None)
        ended = max(ends) if ends else None
        report = Path(run["runs_dir"]) / "report.md"
        entry: dict[str, Any] = {
            "run_id": run["run_id"],
            "runs_dir": run["runs_dir"],
            "started_at": start.isoformat() if start else None,
            "ended_at": ended.isoformat() if ended else None,
            "duration_ms": int((ended - start).total_seconds() * 1000) if start and ended else None,
            "final_H": iterations[-1]["total_H"] if iterations else None,
            "iterations": iterations,
            "unmatched_sessions": unmatched,
            "session_count": len(mine),
            "report": str(report) if report.is_file() else None,
        }
        entry["audit"] = audit_run(entry)
        out.append(entry)
    out.reverse()
    return out


# ── run 级审计 ───────────────────────────────────────────────────────────


def audit_run(run: dict[str, Any]) -> dict[str, Any]:
    """一次 run 的告警:维度不收敛 / 熵反弹 / 改动未采纳 / 判官退化 / 硬软打架。

    与 audit.build_audit 同一 finding 形状与排序,前端与报告页共用一套呈现。
    纯函数,不 I/O。
    """
    from .audit import _LEVEL_ORDER, _finding

    its: list[dict[str, Any]] = [it for it in run.get("iterations") or [] if isinstance(it, dict)]
    findings: list[dict[str, Any]] = []

    # 维度不收敛:≥2 轮里分值 > 0 且一路没变 —— 梯度对它无效(#162 的 placeholder)
    if len(its) >= 2:
        first = its[0].get("breakdown") or {}
        stuck = [
            dim for dim, v in first.items()
            if isinstance(v, (int, float)) and v > 0
            and all((it.get("breakdown") or {}).get(dim) == v for it in its[1:])
        ]
        if stuck:
            findings.append(_finding(
                "ecat-dimension-stuck", "error",
                f"维度不收敛 · {'、'.join(stuck)}",
                f"{len(its)} 轮里 {'、'.join(f'{d}={first[d]:.4f}' for d in stuck)} 纹丝不动 —— "
                "生成端按工作单改了也不降分,要么检查器对这类修法无感,要么工作单措辞"
                "把人带偏;先离线跑该维度的检查器复现。",
            ))

    # 熵反弹 / 改动未采纳:按轮
    for it in its:
        dh = it.get("delta_H")
        if not isinstance(dh, (int, float)):
            continue
        i = it.get("iteration")
        if dh > 0:
            findings.append(_finding(
                "ecat-entropy-rebound", "warn", f"熵反弹 · iter {i}",
                f"ΔH = +{dh:.4f}:上一轮生成把熵改高了,本轮评估在为它买单。",
            ))
        elif dh == 0:
            findings.append(_finding(
                "ecat-iteration-rejected", "warn", f"本轮改动未被采纳 · iter {i}",
                "ΔH = 0,改动没有 commit —— 这一轮的生成与评估时间都没换来收敛。",
            ))

    # 判官退化:discriminator 会话里出现非 entropy-judge 的判官派发(#161)
    disc = [s for it in its for s in it.get("sessions") or [] if s.get("role") == "discriminator"]
    bad = [s for s in disc if any(k != "entropy-judge" for k in (s.get("judge_dispatch") or {})
                                  if (s.get("judge_dispatch") or {}).get(k))]
    if bad:
        kinds = sorted({k for s in bad for k in (s.get("judge_dispatch") or {}) if k != "entropy-judge"})
        findings.append(_finding(
            "ecat-judge-degraded", "error",
            f"判官退化为 {'/'.join(kinds)}",
            f"{len(bad)}/{len(disc)} 个 discriminator 会话的判官没有以 entropy-judge 身份跑"
            "(agent 类型未注册,模型自行换类型重派)—— 判决失去工具限制与 JSON 契约,"
            "且每轮多耗一段重派时间;核 <harmony>/.ecat/agents/discriminator/agents/。",
            agents=[str(s.get("session_id") or "") for s in bad],
        ))

    # 硬检查报问题、判官给 0 分:口径打架,供了解
    seen_dims: set[str] = set()
    for it in its:
        hard = it.get("hard_issues") or {}
        soft = it.get("soft_scores") or {}
        for dim, issues in hard.items():
            if dim in seen_dims or soft.get(dim) != 0:
                continue
            seen_dims.add(dim)
            findings.append(_finding(
                "ecat-hard-soft-conflict", "info",
                f"硬检查与判官相左 · {dim}",
                f"硬检查报 {len(issues)} 条问题(如「{str(issues[0])[:60]}」),判官给 0 分 —— "
                "多半是单页/单入口这类 idiom 被规则误判;若每轮都如此,考虑把该硬检查中和。",
            ))

    findings.sort(key=lambda f: _LEVEL_ORDER.get(f["level"], 9))
    counts = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f["level"]] = counts.get(f["level"], 0) + 1
    return {"findings": findings, "counts": counts}


def iteration_context(path: str) -> dict[str, Any]:
    """这份 ECAT transcript 所在 run/轮次的上下文:熵值、ΔH、本轮工作单文件。

    工作单来自 ``<runs_dir>/<iteration>/gradient.json``(discriminator 第 i 轮产出、
    generator 第 i 轮消费,同一下标)。找不到 run 时只给空上下文,不抛。
    """
    ctx: dict[str, Any] = {"run_id": None, "total_H": None, "delta_H": None}
    harmony = harmony_of(path)
    if not harmony:
        return ctx
    real = os.path.realpath(path)
    for run in list_runs(harmony):
        for it in run["iterations"]:
            for s in it["sessions"]:
                if os.path.realpath(str(s["transcript"])) != real:
                    continue
                ctx.update({
                    "run_id": run["run_id"],
                    "total_H": it.get("total_H"),
                    "delta_H": it.get("delta_H"),
                    "work_list_files": _work_list_files(
                        Path(str(run["runs_dir"])) / str(it["iteration"]) / "gradient.json"
                    ),
                })
                return ctx
        for s in run["unmatched_sessions"]:
            if os.path.realpath(str(s["transcript"])) == real:
                ctx["run_id"] = run["run_id"]
                return ctx
    return ctx


def _work_list_files(gradient: Path) -> list[str]:
    if not gradient.is_file():
        return []
    with suppress(json.JSONDecodeError, OSError, TypeError, AttributeError):
        data = json.loads(gradient.read_text(encoding="utf-8", errors="replace"))
        items = data.get("work_list") if isinstance(data, dict) else None
        out: list[str] = []
        for w in items or []:
            f = str(w.get("file") or "") if isinstance(w, dict) else ""
            if f and f not in out:
                out.append(f)
        return out
    return []


def run_id_of(path: str) -> str | None:
    """这份 ECAT transcript 属于哪次 run(按 list_runs 的归属规则)。"""
    rid = iteration_context(path).get("run_id")
    return str(rid) if rid else None


def _public(s: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in s.items() if not k.startswith("_")}


def stage_label(role: str, iteration: int | None) -> str:
    base = f"ECAT {role.capitalize()}"
    return f"{base} · iter {iteration}" if iteration is not None else base


def annotate(path: str, trace: dict[str, Any]) -> dict[str, Any]:
    """ECAT 会话的 trace 补 ``meta.ecat`` 与阶段标签(原 hmigbot-plus locate.extract_trace 里的那段)。

    ECAT 会话没有管线 Skill,adapter 只能给一段无名的 Session 阶段;这里把角色与轮次补进
    ``meta.ecat`` 并写成阶段标签,报告页一眼能看出这是哪一轮的 generator 还是 discriminator。
    审计规则(agent-type-missing / ecat-out-of-scope / ecat-no-effect)只看这里,本身不 I/O。
    不是 ECAT 会话原样返回:CC 线只看路径,codex 线只读 rollout 首行与 run 目录。
    """
    role = role_of(path)
    if not role:
        return trace
    info = session_meta(path, trace)
    meta = trace.setdefault("meta", {})
    if isinstance(meta, dict):
        iteration = info.get("iteration")
        meta["ecat"] = {
            "role": role,
            "iteration": iteration,
            # codex generator 跨轮 resume 同一 thread:一份 rollout 覆盖几轮
            "iterations": info.get("iterations") or ([iteration] if iteration is not None else []),
            "judge_dispatch": info.get("judge_dispatch") or {},
            "subagents": info.get("subagents"),
            **iteration_context(path),
        }
    stages = trace.get("stages")
    if isinstance(stages, list) and len(stages) == 1 and stages[0].get("stage") == "session":
        stages[0]["label"] = stage_label(role, info.get("iteration"))
    return trace
