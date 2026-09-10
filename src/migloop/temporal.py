"""Time-scoped evidence views shared by MCP and HTTP.

There is deliberately no version-to-time shortcut here. Raw records define the
corpus; the inferred ledger supplies optional annotations, never admission rights.
Query order is not an edge. A file view is evidence history, not a disk snapshot.
"""
from __future__ import annotations

import ntpath
import posixpath
from dataclasses import dataclass
from typing import Any

from . import atoms
from . import transcript_store as store
from .evidence import CONFIRMED_BASES, proof_payload
from .time_scope import _iso, _time

SCHEMA = "migloop-time-view/1"


def resolve_file(ledger: atoms.Ledger, hint: str) -> str:
    """Never disambiguate a file by whichever happens to have more versions."""
    path = posixpath.normpath(hint.replace("\\", "/"))
    if path in ledger.stories:
        return path
    # An explicit root is not a basename hint. /A.ets must not silently select
    # /project/A.ets; remote Windows drives and UNC roots are literal as well.
    if path.startswith("/") or ntpath.splitdrive(path)[0]:
        return path
    suffix = path.lstrip("/")
    matches = [p for p in ledger.stories if p == suffix or p.endswith("/" + suffix)]
    if len(matches) > 1:
        raise ValueError("文件路径歧义，请使用完整路径: " + ", ".join(sorted(matches)[:6]))
    return matches[0] if matches else path


@dataclass(frozen=True)
class Window:
    at: str = "latest"
    since: str | None = None

    @classmethod
    def parse(cls, at: str | None, since: str | None = None) -> Window:
        if at in (None, "latest"):
            end = "latest"
        else:
            end = _iso(_time(at))
            if end is None:
                raise ValueError("at 必须是带时区的 ISO 时刻或 latest")
        start = _iso(_time(since)) if since is not None else None
        if since is not None and start is None:
            raise ValueError("since_ts 必须是带时区的 ISO 时刻")
        if start and end != "latest" and start > end:
            raise ValueError("since_ts 不能晚于 at")
        return cls(end, start)

    def contains(self, ts: str | None) -> bool:
        stamp = _iso(_time(ts))
        return bool(stamp and (self.at == "latest" or stamp <= self.at)
                    and (self.since is None or stamp >= self.since))

    def ended(self, ts: str | None) -> bool:
        return Window(self.at).contains(ts)


def _targets(ledger: atoms.Ledger, act: atoms.Action) -> set[str]:
    return {r.path for r in act.files} | set(ledger.mention_seq.get(act.seq, [])) | set(
        act.detail.get("touched") or []) | set(act.detail.get("conditional") or []) | set(
        act.detail.get("effect_candidates") or [])


def _annotations(ledger: atoms.Ledger, window: Window, agent_ids: set[str] | None = None) -> dict[tuple[str, int], list[dict[str, Any]]]:
    import os
    index: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for agent in ledger.agents.values():
        if agent_ids is not None and agent.id not in agent_ids:
            continue
        for act in agent.actions:
            if not act.src:
                continue
            path, use, result = act.src
            start_ts, done_ts = _iso(_time(act.ts)), _iso(_time(act.done_ts))
            completed = bool(start_ts and done_ts and start_ts <= done_ts and window.ended(done_ts))
            # Whether a result exists after the query cutoff is not input to
            # this projection. "pending" also covers an unrecorded result.
            state = ("failed" if act.ok is False else "returned") if completed else "pending_or_unknown"
            if not act.tuid and use == result:
                state = "recorded_message"
            base = {"agent": agent.id, "seq": act.seq, "tool": act.tool,
                    "use_ts": _iso(_time(act.ts)), "done_ts": _iso(_time(act.done_ts)) if completed else None,
                    "state": state, "legacy_ref": atoms.format_ref(act.seq, ledger.locs.get(act.seq))}
            relations = []
            # Inferred FileRefs may depend on the *result* (e.g. listed paths,
            # snapshot content). Before it returns they are not available facts.
            for ref in act.files if completed else []:
                proof = proof_payload(ref.proof)
                execution = proof["execution"] if completed else "unknown"
                confirmed = execution == "confirmed" and proof["operation_basis"] in CONFIRMED_BASES
                relations.append({"kind": ref.op, "path": ref.path,
                    "status": "confirmed" if confirmed else "candidate",
                    "operation_basis": proof["operation_basis"], "execution": execution,
                    "delivery": proof["delivery"] if completed else "not_yet_returned",
                    "version_binding": "not_used_in_time_view", "legacy_v": None})
            for target in sorted(_targets(ledger, act) - {r.path for r in act.files}) if completed else []:
                intents = [r for r in act.detail.get("code_host_intents") or [] if r.get("path") == target]
                if intents:
                    relations.append({"kind": "code_host_intent", "path": target,
                                      "status": "unverified_intent", "execution": "unknown",
                                      "operation_basis": "code_host_intent",
                                      "note": "脚本中声明了此目标；未核实内部调用曾执行，不是历史读写边"})
                    continue
                possible = target in (set(act.detail.get("touched") or []) | set(
                    act.detail.get("conditional") or []) | set(act.detail.get("effect_candidates") or []))
                relations.append({"kind": "possible_access" if possible else "mention", "path": target,
                                  "status": "candidate" if possible else "lexical"})
            base["relations"] = relations
            # Source pointer indexes BOTH records, without joining their bodies.
            for line in {use, result}:
                if line is not None:
                    index.setdefault((os.path.normcase(os.path.abspath(path)), line + 1), []).append(base)
    return index


def _page(rows: list[dict[str, Any]], offset: int, limit: int) -> dict[str, Any]:
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("offset ≥ 0；limit 必须在 1–200 之间")
    return {"total": len(rows), "offset": offset, "limit": limit,
            "remaining": max(0, len(rows) - offset - limit),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "rows": rows[offset:offset + limit]}


def _annotation_view(annotations: list[dict[str, Any]], kind: str, key: str | None,
                     details: bool) -> tuple[list[dict[str, Any]], int]:
    """Disclosure only: admission/search still uses all original annotations.

    A bulk script may touch hundreds of files. Repeating every unrelated path
    in each file's first page obscures its evidence and blows the return budget.
    Counts and details=true preserve an explicit expansion path.
    """
    if details:
        return annotations, 0
    shown = []
    ranked = annotations
    if kind == "file":
        ranked = sorted(annotations, key=lambda a: not any(r["path"] == key for r in a["relations"]))
    for annotation in ranked[:4]:
        relations = annotation["relations"]
        focused = [r for r in relations if r["path"] == key] if kind == "file" else relations
        selected = focused[:6]
        shown.append({**annotation, "relations": selected, "relation_count": len(relations),
                      "relations_omitted": len(relations) - len(selected)})
    return shown, max(0, len(annotations) - len(shown))


def query(ledger: atoms.Ledger, *, kind: str, key: str | None = None, at: str = "latest",
          since_ts: str | None = None, q: str | None = None, q_any: list[str] | None = None,
          offset: int = 0, limit: int = 40, include_undated: bool = False,
          details: bool = False, annotation_offset: int = 0, annotation_limit: int | None = None,
          relation_offset: int = 0, relation_limit: int | None = None) -> dict[str, Any]:
    """Search all selected raw content; disclosure budgets affect only output."""
    from .search_terms import normalize
    from . import temporal_annotation
    annotation_options = dict(annotation_offset=annotation_offset, annotation_limit=annotation_limit,
                              relation_offset=relation_offset, relation_limit=relation_limit)
    temporal_annotation.validate(**annotation_options)
    window = Window.parse(at, since_ts)
    if type(details) is not bool:
        raise ValueError("details 必须是布尔值")
    _page([], offset, limit)
    if kind not in ("agent", "file", "pool"):
        raise ValueError("时间查询只支持 agent/file/pool")
    if kind == "agent":
        owner = atoms.resolve_agent(ledger, key or "")
        if owner is None:
            raise ValueError("账本里没有该 agent")
        key = owner.id
    if kind == "file":
        if not key:
            raise ValueError("file 查询需要 path")
        # A raw-only path may have no story. Do not force an invented version.
        key = resolve_file(ledger, key)
    terms = normalize(q or "", q_any) or ([q] if q else [])
    needles = [term.casefold() for term in terms]
    registry = store.sources(ledger, key if kind == "agent" else None)
    all_registry = store.sources(ledger)
    source_counts: dict[str, int] = {}
    for path in all_registry:
        tag = store.source_key(path)
        source_counts[tag] = source_counts.get(tag, 0) + 1
    import os
    stale = []
    for path, expected in ledger.source_stats.items():
        try:
            stat = os.stat(path)
            if (stat.st_mtime_ns, stat.st_size) != expected:
                stale.append(path)
        except OSError:
            stale.append(path)
    annotations = {} if stale else _annotations(ledger, window, {key} if kind == "agent" else None)
    rows, undated, gaps = [], [], []
    counts = {"records_scanned": 0, "in_scope": 0, "outside_time": 0,
              "undated": 0, "malformed": 0, "matched": 0}
    needle_file = (key or "").rsplit("/", 1)[-1].casefold()
    for path, owners in sorted(registry.items()):
        try:
            for record in store.records(path):
                counts["records_scanned"] += 1
                annotation = annotations.get((path, record.line), [])
                text = None
                if kind == "file":
                    exact = any(r["path"] == key for a in annotation for r in a["relations"])
                    if not exact:
                        text = record.text
                        if needle_file not in text.replace("\\", "/").casefold():
                            continue
                if record.malformed:
                    counts["malformed"] += 1
                if record.ts is None:
                    counts["undated"] += 1
                    if not include_undated:
                        continue
                elif not window.contains(record.ts):
                    counts["outside_time"] += 1
                    continue
                else:
                    counts["in_scope"] += 1
                text = text if text is not None else record.text
                folded = text.casefold()
                matched = [term for term, needle in zip(terms, needles) if needle in folded]
                if needles and not matched:
                    continue
                preview_text = text
                if not needles and kind != "file" and isinstance(record.value, dict):
                    message = record.value.get("message")
                    payload = message.get("content") if isinstance(message, dict) else record.value.get("payload")
                    if payload is not None:
                        preview_text = store.readable(payload)
                previews = needles or ([needle_file] if kind == "file" and needle_file else [])
                position = min((folded.find(needle) for needle in previews if needle in folded), default=0)
                preview = preview_text[max(0, position - 60):max(0, position - 60) + 240]
                row = {**record.address(), "agents": sorted(owners), "annotations": annotation,
                       "annotations_omitted": 0,
                       "preview": preview, "preview_kind": "decoded_field_excerpt", "chars": len(text), "matched": matched,
                       "reference_status": "ambiguous_source" if source_counts[store.source_key(path)] > 1 else "addressable",
                       "association": "agent_transcript" if kind == "agent" else
                           "indexed_or_lexical_not_causal" if kind == "file" else "pool_record"}
                (undated if record.ts is None else rows).append(row)
        except (OSError, UnicodeError, ValueError) as exc:
            gaps.append({"source": path, "error": str(exc)})
    rows.sort(key=lambda row: (row["ts"], row["source"], row["line"]))
    query_kind = "search" if terms or kind == "pool" else kind
    query_args = {"at": window.at, "since_ts": window.since, "include_undated": include_undated}
    if query_kind == "search":
        if len(terms) > 1:
            query_args["q_any"] = terms
        else:
            query_args["q"] = terms[0] if terms else ""
        if kind in ("file", "agent"):
            query_args[kind] = key
    else:
        query_args["path" if kind == "file" else "id"] = key
    annotation_query = {"tool": query_kind, "args": query_args,
                        "scope": {"kind": kind, "key": key, "at": window.at, "since_ts": window.since}}
    for page_rows in (rows, undated):
        for row_offset, row in enumerate(page_rows[offset:offset + limit], offset):
            if row["annotations"]:
                shown, omitted, annotation_page = temporal_annotation.project(row["annotations"], kind, key,
                                                                             details, **annotation_options)
                row.update(annotations=shown, annotations_omitted=omitted, annotation_page=annotation_page)
                temporal_annotation.bind(row, annotation_query, row_offset)
    counts["matched"] = len(rows)
    body = _page(rows, offset, limit)
    body.update(schema=SCHEMA, node={"kind": kind, "key": key, "at": window.at,
                "identity_status": "unresolved_lexical_scope" if kind == "file" and key not in ledger.stories else "indexed"},
                scope={"since_ts": window.since, "at": window.at, "bounds": "inclusive",
                       "corpus": "owned_raw_jsonl", "selection": kind, "search_terms": terms},
                counts=counts, gaps=gaps, undated=_page(undated, offset, limit), details=details,
                stale_annotation_sources=stale,
                source_count=len(registry), raw_scan_complete=not gaps and bool(registry),
                causal_complete=False,
                note="时间只限定已记录证据，不证明因果或磁盘状态。相同时刻不推断先后；"
                     "未知时间单列，不作为截止前输入。摘要可展开；搜索不受分页/摘要限制。"
                     "关系注释默认摘要；annotation_page/relation_page提供同范围独立续读，details=true也可按预算折叠。"
                     "文件入口含已索引关系与文件名提及，不能证明所有未识别效应都已关联到文件。")
    body["receipt"] = {"schema": "migloop-query-receipt/1", "node": body["node"],
                       "scope": body["scope"], "records": [r["ref"] for r in body["rows"]],
                       "undated_records": [r["ref"] for r in body["undated"]["rows"]],
                       "navigation_is_relation": False}
    return body


def record_data(ledger: atoms.Ledger, ref: str, *, at: str = "latest", offset: int = 0,
                max_chars: int = 20000, include_undated: bool = False) -> dict[str, Any]:
    window = Window.parse(at)
    if type(offset) is not int or offset < 0 or type(max_chars) is not int or not 1 <= max_chars <= 120000:
        raise ValueError("offset ≥ 0；max_chars 必须在 1–120000 之间")
    record = store.resolve(ledger, ref)
    if record.ts is None and not include_undated:
        raise ValueError("记录时间未知；显式 include_undated=true 才能展开，不计入截止前输入")
    if record.ts is not None and not window.contains(record.ts):
        raise ValueError("原文记录晚于查询截止时刻；未返回内容")
    # Original JSONL bytes decoded as UTF-8, not a reconstructed Action summary.
    text = record.raw
    return {"schema": "migloop-raw-record/1", **record.address(), "at": window.at,
            "text": text[offset:offset + max_chars], "offset": offset, "chars": len(text),
            "next_offset": offset + max_chars if offset + max_chars < len(text) else None,
            "receipt": {"schema": "migloop-query-receipt/1", "node": None,
                        "scope": {"at": window.at}, "records": [record.ref], "navigation_is_relation": False}}


def render(data: dict[str, Any]) -> str:
    """Text and UI consume the exact same selected rows and scope metadata."""
    import json
    if data["schema"] == "migloop-raw-record/1":
        return (f"# 原始记录 {data['ref']} · {data['ts'] or '时间未知'} · 截至 {data['at']}\n"
                f"字符 {data['offset']} 起 / 共 {data['chars']}；next_offset={data['next_offset']}\n" + data["text"])
    node, counts = data["node"], data["counts"]
    out = [f"# 时间原子 {node['kind']}:{node['key'] or '*'} · 截至 {node['at']}",
           "范围 " + json.dumps(data["scope"], ensure_ascii=False),
           (f"匹配 {data['total']} 条；本页 {len(data['rows'])} 条；next_offset={data['next_offset']}；"
            f"未知时间 {counts['undated']}；源缺口 {len(data['gaps'])}"), data["note"]]
    for label, rows in (("已记录时间", data["rows"]), ("时间未知·不属于截止前证据", data["undated"]["rows"])):
        if rows:
            out.append("## " + label)
        for row in rows:
            out.append(f"- {row['ts'] or '?'} {row['ref']} · {','.join(row['agents'])} · {row['kind']} · {row['chars']} 字")
            for annotation in row["annotations"]:
                rels = "; ".join(f"{r['kind']} {r['path']} [{r['status']};版本绑定 {r.get('version_binding', '不适用')}]"
                                 for r in annotation["relations"])
                out.append(f"  {annotation['tool']} [{annotation['state']}] {rels}")
            out.append("  摘要: " + row["preview"].replace("\n", " "))
    if data["gaps"]:
        out.append("源缺口 " + json.dumps(data["gaps"], ensure_ascii=False))
    if data["stale_annotation_sources"]:
        out.append("源文件已变化：本次仍搜原始记录，但停用旧账本的关系标签；重新建账后恢复。")
    out.append("原文: record(ref=...,at=同一截止)。独立打开 file/agent 无需 via；查询顺序不生成读写边。")
    return "\n".join(out)
