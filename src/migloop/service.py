"""本地服务层:会话定位、trace 缓存、报告页 trace(审计 + 跨会话提示 + 执行拓扑后续节点)。

离线报告、--live 的会话详情页(以及 a2h-memory 的 fixchain 服务)共用这一层。池子 = 同工程磁盘上的
兄弟会话(project_sessions 的 root 发现),trace 按 (转录 mtime, size) 缓存。

返修链路(两原子账本、返修链页、两原子端点、MCP 后端、调查页)已移到 fuxi-ailabs/a2h-memory 的
``fixchain/``;那边在这一层之上建账,会话定位与冻结池的观察范围仍以这里为准。
"""

from __future__ import annotations

import glob
import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

from . import adapters, audit, ecat, followups, project_sessions
from .render import build_html, load_template

class SessionLookupError(Exception):
    """目标解析不到唯一会话,或该来源不支持这项能力。"""


_LOCK = threading.RLock()
_TRACE_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}
_ROOT_SIGNATURE_CACHE: dict[str, tuple[Any, tuple[str, str | None]]] = {}
_CACHE_MAX = 3
_ROOT_SIGNATURE_CACHE_MAX = 256
#: 冻结池只收这两种根会话(a2h-memory fixchain 的两原子账本也只有这两种收集器)
_ATOM_FORMATS = ("claude", "codex")


# ═══════════════ 会话定位 ═══════════════

def _frozen_pool() -> str | None:
    """显式实验模式;不从 cwd、用户目录或清单 original 字段推断另一个池子。"""
    value = os.environ.get("MIGLOOP_FROZEN_POOL", "").strip()
    if not value:
        if os.environ.get("MIGLOOP_FROZEN_ANCHOR", "").strip() or os.environ.get("MIGLOOP_FROZEN_ROOTS", "").strip():
            raise SessionLookupError("MIGLOOP_FROZEN_ANCHOR/ROOTS 只能与 MIGLOOP_FROZEN_POOL 一起使用")
        return None
    pool = os.path.realpath(os.path.abspath(value))
    if not os.path.isdir(pool):
        raise SessionLookupError(f"冻结池目录不存在: {value}")
    return pool


def _frozen_path(path: str, pool: str) -> str:
    absolute = os.path.abspath(path)
    resolved = os.path.realpath(absolute)
    try:
        inside = os.path.normcase(os.path.commonpath([pool, resolved])) == os.path.normcase(pool)
    except ValueError:
        inside = False
    if not inside:
        raise SessionLookupError(f"路径越出冻结池: {path}")
    if os.path.normcase(absolute) != os.path.normcase(resolved):
        raise SessionLookupError(f"冻结池不接受符号链接或重解析路径: {path}")
    return resolved


def _frozen_root(path: str, pool: str) -> str:
    resolved = _frozen_path(path if os.path.isabs(path) else os.path.join(pool, path), pool)
    if os.path.normcase(os.path.dirname(resolved)) != os.path.normcase(pool) \
            or not resolved.lower().endswith(".jsonl") or not os.path.isfile(resolved):
        raise SessionLookupError(f"不是冻结池内的根 JSONL: {path}")
    return resolved


def _frozen_roots(pool: str) -> list[str]:
    return sorted(_frozen_root(path, pool) for path in glob.glob(os.path.join(pool, "*.jsonl")))


def _frozen_anchor(pool: str) -> str | None:
    value = os.environ.get("MIGLOOP_FROZEN_ANCHOR", "").strip()
    if not value:
        return None
    return _frozen_root(value, pool)


def _configured_frozen_roots(pool: str) -> list[str] | None:
    value = os.environ.get("MIGLOOP_FROZEN_ROOTS", "").strip()
    if not value:
        return None
    try:
        configured = json.loads(value)
    except ValueError as exc:
        raise SessionLookupError("MIGLOOP_FROZEN_ROOTS 必须是 JSON 数组") from exc
    if not isinstance(configured, list) or not configured:
        raise SessionLookupError("MIGLOOP_FROZEN_ROOTS 必须是非空 JSON 数组")
    roots: list[str] = []
    for item in configured:
        if not isinstance(item, str) or not item.strip():
            raise SessionLookupError("MIGLOOP_FROZEN_ROOTS 每项必须是根 JSONL 路径")
        roots.append(_frozen_root(item, pool))
    if len({os.path.normcase(path) for path in roots}) != len(roots):
        raise SessionLookupError("MIGLOOP_FROZEN_ROOTS 不接受重复根")
    return roots


def _root_signature(path: str) -> tuple[str, str | None]:
    """Cheap immutable-root identity: adapter format plus exact slash-normalized recorded cwd.

    Only the bounded first JSONL record is inspected. Missing cwd stays unknown;
    it is never guessed from the host path or another root.
    """
    path = os.path.realpath(os.path.abspath(path))
    key = _stat_key([path])
    with _LOCK:
        hit = _ROOT_SIGNATURE_CACHE.get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
    fmt = str(adapters.detect(path).FORMAT)
    cwd: Any = None
    try:
        if fmt == "dsh":                                  # header row, possibly inside a Zstandard frame
            from .adapters import dsh_source
            record = dsh_source.read_header(path)
        else:
            with open(path, encoding="utf-8-sig") as stream:
                record = json.loads(stream.readline(1024 * 1024))
        if isinstance(record, dict):
            cwd = record.get("cwd")
            payload = record.get("payload")
            if not cwd and isinstance(payload, dict):
                cwd = payload.get("cwd")
    except (OSError, ValueError, RuntimeError):
        cwd = None
    normalized = str(cwd).replace("\\", "/").rstrip("/") if isinstance(cwd, str) and cwd.strip() else None
    result = (fmt, normalized)
    with _LOCK:
        if len(_ROOT_SIGNATURE_CACHE) >= _ROOT_SIGNATURE_CACHE_MAX and path not in _ROOT_SIGNATURE_CACHE:
            _ROOT_SIGNATURE_CACHE.pop(next(iter(_ROOT_SIGNATURE_CACHE)))
        _ROOT_SIGNATURE_CACHE[path] = (key, result)
    return result


def _root_first_time(path: str) -> datetime:
    raw = project_sessions.first_record_ts(path)
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise SessionLookupError(f"冻结 root 缺少可排序首条时刻: {path}") from exc
    if stamp.tzinfo is None:
        raise SessionLookupError(f"冻结 root 首条时刻缺时区，不能认证相对 anchor 的先后: {path}")
    return stamp.astimezone(timezone.utc)


def _anchored_roots(pool: str, anchor: str, configured: list[str]) -> list[str]:
    """Validate and order the caller-selected fixed observation book."""
    if anchor not in configured:
        raise SessionLookupError("MIGLOOP_FROZEN_ANCHOR 必须包含在 MIGLOOP_FROZEN_ROOTS 中")
    anchor_fmt, _anchor_cwd = _root_signature(anchor)
    anchor_ts = _root_first_time(anchor)
    rows: list[tuple[datetime, str]] = []
    for candidate in configured:
        fmt, _cwd = _root_signature(candidate)
        if fmt != anchor_fmt:
            raise SessionLookupError("MIGLOOP_FROZEN_ROOTS 含与 anchor 不同的会话格式")
        ts = _root_first_time(candidate)
        if ts > anchor_ts:
            raise SessionLookupError(f"冻结 root 晚于 anchor: {candidate}")
        rows.append((ts, candidate))
    return [path for _ts, path in sorted(rows, key=lambda row: (row[0], os.path.normcase(row[1])))]


def observation_scope(path: str) -> dict[str, Any]:
    """Return the single observation range used by all high-level service entrypoints."""
    pool = _frozen_pool()
    if pool is None:
        requested = _root_path(path)
        return {"requested_root": requested, "anchor": requested, "roots": [requested], "mode": "live_dynamic"}
    requested = _frozen_root(path, pool)
    anchor = _frozen_anchor(pool)
    configured = _configured_frozen_roots(pool)
    if anchor is None and configured is None:
        return {"requested_root": requested, "anchor": requested, "roots": [requested], "mode": "frozen_dynamic"}
    if anchor is None or configured is None:
        raise SessionLookupError("冻结 anchor 模式必须同时配置 MIGLOOP_FROZEN_ANCHOR 和 MIGLOOP_FROZEN_ROOTS")
    roots = _anchored_roots(pool, anchor, configured)
    if requested not in roots:
        raise SessionLookupError("冻结入口不在调用者指定的 MIGLOOP_FROZEN_ROOTS 观察范围")
    return {
        "requested_root": requested,
        "anchor": anchor,
        "roots": roots,
        "root_details": [
            {"root": root, "format": _root_signature(root)[0], "cwd": _root_signature(root)[1]}
            for root in roots
        ],
        "mode": "frozen_anchor",
        "roots_source": "explicit_configuration",
    }


def _observation_root(path: str) -> str:
    return str(observation_scope(path)["anchor"])


_UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"


def _frozen_codex_id(path: str) -> str | None:
    """Alias only an already-validated pool root, never discover another file."""
    stem = os.path.splitext(os.path.basename(path))[0]
    match = re.search(r"(" + _UUID + r")$", stem, re.I) if stem.lower().startswith("rollout-") else None
    if match:
        return match[1].lower()
    # Nonstandard root filenames may still carry an explicit canonical session ID.
    # Read only the bounded first record, not messages or nested/subagent paths.
    try:
        with open(path, encoding="utf-8-sig") as stream:
            record = json.loads(stream.readline(1024 * 1024))
    except (OSError, ValueError):
        return None
    payload = record.get("payload") if isinstance(record, dict) and record.get("type") == "session_meta" else None
    sid = payload.get("id") or payload.get("session_id") if isinstance(payload, dict) else None
    return sid.lower() if isinstance(sid, str) and re.fullmatch(_UUID, sid, re.I) else None


def _validate_frozen_tree(pool: str) -> None:
    """CC 子代理/工作流与 Codex 递归 rollout 扫描均只接触经核验的池内文件。"""
    for directory, dirs, files in os.walk(pool, followlinks=False):
        _frozen_path(directory, pool)
        for name in [*dirs, *files]:
            _frozen_path(os.path.join(directory, name), pool)


def _root_path(path: str) -> str:
    """文件路径规范成绝对路径;DevEco 的裸 session id 不是路径,原样保留(abspath 会拼上 cwd,
    detect 就认不出它了 —— 2026-09-09 CLI ``migloop ses_xxx`` 的回归)。"""
    if not os.path.isfile(path) and adapters.get("deveco").is_session(path):
        return path
    return os.path.abspath(path)


def locate_session(target: str, roots: dict[str, str] | None = None) -> str:
    """jsonl 路径 | session-id 前缀 | 项目名片段 → 唯一 root 转录路径(最新者优先)。"""
    pool = _frozen_pool()
    if pool is not None:
        want = str(target or "").strip()
        if os.path.isabs(want) or "/" in want or "\\" in want or want.lower().endswith(".jsonl"):
            return _observation_root(_frozen_root(want, pool))
        known_roots = _frozen_roots(pool)
        hits = {p for p in known_roots if want and os.path.basename(p)[:-6].startswith(want)}
        if re.fullmatch(r"[0-9a-f-]+", want, re.I):
            for path in known_roots:
                sid = _frozen_codex_id(path)
                if sid and sid.startswith(want.lower()):
                    hits.add(path)
        if len(hits) != 1:
            reason = "前缀有歧义" if hits else "找不到根会话"
            raise SessionLookupError(f"冻结池{reason}: {target}")
        return _observation_root(next(iter(hits)))
    if os.path.isfile(target):
        return os.path.abspath(target)
    rows = list(adapters.discover(roots or {}))
    want = str(target or "").strip()
    hits = [r for r in rows if want and (str(r.session_id or "").startswith(want) or (
        getattr(r, "format", None) == "dsh" and str(r.session_id or "").startswith("session-" + want)))]
    if not hits:
        hits = [r for r in rows if want and want.lower() in str(r.project or "").lower()]
    if not hits:
        raise SessionLookupError(f"找不到会话: {target}")
    return _root_path(hits[0].path)               # discover 已按 mtime 新→旧


def _stat_key(paths: list[str]) -> list[Any]:
    out: list[Any] = []
    for p in paths:
        try:
            st = os.stat(p)
            out.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((p, None, None))
    return out


def _put(cache: dict[str, Any], key: str, value: Any) -> None:
    if len(cache) >= _CACHE_MAX and key not in cache:
        cache.pop(next(iter(cache)))
    cache[key] = value


# ═══════════════ trace(提取层 + ECAT 补注)与同工程前后会话 ═══════════════

def extract_trace(path: str, storage_root: str | None = None) -> dict[str, Any]:
    pool = _frozen_pool()
    if pool is not None:
        path = _frozen_root(path, pool)
        _validate_frozen_tree(pool)
    key = [*_stat_key([path]), ("frozen_pool", pool)]
    with _LOCK:
        hit = _TRACE_CACHE.get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
        adapter: Any = adapters.detect(path)
        if pool is not None and adapter.FORMAT not in _ATOM_FORMATS:
            raise SessionLookupError(f"冻结池不支持 {adapter.FORMAT} 会话")
        if pool is not None and adapter.FORMAT == "codex":
            data = dict(adapter.extract(path, sessions_root=pool))
        elif adapter.FORMAT == "deveco":                 # 只有 DevEco 需要数据目录定位子代理库
            data = dict(adapter.extract(path, storage_root=storage_root))
        else:
            data = dict(adapter.extract(path))
        annotate_trace(path, data)
        _put(_TRACE_CACHE, path, (key, data))
        return data


def annotate_trace(path: str, data: dict[str, Any]) -> dict[str, Any]:
    """来源无关的补注:ECAT 角色会话补 ``meta.ecat`` 与阶段标签。复用已解析的 trace,
    非 ECAT 会话只看路径 / rollout 首行;补不上不拖垮报告。"""
    try:
        ecat.annotate(path, data)
    except Exception:  # noqa: BLE001 - 补注是锦上添花
        pass
    return data


def _fmt_of(trace: dict[str, Any]) -> str:
    return str((trace.get("meta") or {}).get("session_format") or "claude")


def prior_roots(fmt: str, path: str, cwd: str) -> list[str]:
    """同工程的前序 root 会话(近→远,最多 64 个):一次迁移 run 里 Driver 直接起的会话(reviewer、ECAT
    判别器 / 修复方、loop engine 续接的 worker)都是 root,DiceRoller 0903 一个 run 就有 17 个。报告页的
    跨会话提示取第一个;a2h-memory fixchain 把它们全部并进账本池,只取 3 个会把返修链切断。"""
    pool = _frozen_pool()
    if pool is not None:
        anchor = _frozen_anchor(pool)
        if anchor is not None:
            scope = observation_scope(path)
            return [root for root in scope["roots"] if root != scope["anchor"]]
        return _frozen_adjacent_roots(pool, path, later=False)
    if fmt == "codex":
        return project_sessions.find_prior_codex_roots(path, cwd, limit=64)
    if fmt == "claude":
        return project_sessions.find_prior_claude_roots(path, limit=64)
    return []


def later_roots(fmt: str, path: str, cwd: str) -> list[str]:
    pool = _frozen_pool()
    if pool is not None:
        if _frozen_anchor(pool) is not None:
            observation_scope(path)  # validate the requested alias even though fixed scope has no later root
            return []
        return _frozen_adjacent_roots(pool, path, later=True)
    if fmt == "codex":
        return project_sessions.find_later_codex_roots(path, cwd, 1)
    if fmt == "claude":
        return project_sessions.find_later_claude_roots(path, 1)
    return []


def _frozen_adjacent_roots(pool: str, path: str, later: bool) -> list[str]:
    current = _frozen_root(path, pool)
    current_ts = project_sessions.first_record_ts(current)
    if not current_ts:
        return []
    rows = [(project_sessions.first_record_ts(p), p) for p in _frozen_roots(pool) if p != current]
    if later:
        return [p for ts, p in sorted(rows) if ts and ts > current_ts][:1]
    return [p for ts, p in sorted(rows) if ts and ts < current_ts][-64:][::-1]


def root_sid8(fmt: str, path: str) -> str:
    """root 转录 → 8 位会话号:codex 读首行 meta 的 id,CC 取文件名。"""
    if fmt == "codex":
        cx: Any = adapters.get("codex")
        return str((cx.session_summary(path) or {}).get("id") or "")[:8]
    if fmt == "dsh":                                      # session-<uuid>: the uuid part names the route
        from .adapters import dsh_source
        sid = str(dsh_source.read_header(path)["id"])
        return (sid[len("session-"):] if sid.startswith("session-") else sid)[:8]
    return os.path.splitext(os.path.basename(path))[0][:8]


# ═══════════════ 页面 ═══════════════

def report_trace(path: str, *, static: bool = False, storage_root: str | None = None) -> dict[str, Any]:
    """报告页的 trace:提取层 + 审计(「02 风险点」)+ 跨会话提示 + 执行拓扑的后续节点。

    static=True 是导出的自包含 HTML / live 快照:没有服务端,后续节点不带站内链接。
    返修追溯卡(两原子账本算的链)不在这里,由 a2h-memory fixchain 的服务补进 audit。"""
    scope = observation_scope(path)
    path = str(scope["anchor"])
    data = dict(extract_trace(path, storage_root))
    if scope["mode"] == "frozen_anchor":
        data["observation_scope"] = scope
    fmt = _fmt_of(data)
    pool_traces = []
    cwd = str((data.get("meta") or {}).get("cwd") or "")
    audit_gaps = False
    # Only explicitly frozen roots belong to this audit scope. Same-directory
    # historical migrations may be useful for lineage, not for clearing warnings.
    for pp in scope["roots"]:
        if pp != path:
            try:
                pool_traces.append(extract_trace(pp, storage_root))
            except Exception:
                audit_gaps = True
    data["audit"] = audit.build_audit(data, pool_traces=pool_traces, material_gaps=audit_gaps)
    fixed_scope = scope["mode"] == "frozen_anchor"
    later = [] if fixed_scope else later_roots(fmt, path, cwd)
    prior = [] if fixed_scope else prior_roots(fmt, path, cwd)[:1]
    hint = {"later": root_sid8(fmt, later[0]) if later else None,
            "prior": root_sid8(fmt, prior[0]) if prior else None}
    if hint["later"] or hint["prior"]:
        data["audit"]["cross_hint"] = hint
    # 执行拓扑的后续节点(同工程其后的能力会话 + ECAT run);冻结池只看给定的根,不往外找。
    # 挂不上不能拖垮报告
    try:
        data["followups"] = [] if fixed_scope else followups.collect(path, data, link=not static)
    except Exception:  # noqa: BLE001
        data["followups"] = []
    return data


def report_html(path: str) -> str:
    return build_html(report_trace(path), load_template())
