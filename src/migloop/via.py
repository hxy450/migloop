"""来处(via):已打开的版本节点,或真实搜索返回的精确命中。

节点只有两种,都带版本:file(path, v) 打开的 file@vN、agent(id, v) 打开的 agent@vK(v 必填,schema 里就是 required)。
via 节点来处必须带版本且等于打开过的节点;search:<凭据>:<命中号> 是调查事件来处,不是第三种原子。
blame / diff / action / search 不移动、不开节点。搜索凭据只允许打开该命中的精确版本,不证明历史读取关系。
第一次 file / agent 允许 via=sessions / task(从返修链摘要进来),之后不允许。校验在服务端做:不对就不执行。
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

from . import atoms, filestory

NODE_RE = re.compile(r"^(file|agent):(\S+?)(?:@v(\d+))?(?=\s|$)")
FIRST_TAGS = ("sessions", "task")
SEARCH_RE = re.compile(r"^search:([0-9a-f]{24}):(\d+)(?=\s|$)")
SEARCH_RECEIPT = "MIGLOOP_SEARCH_RECEIPT "
SEARCH_SCHEMA = "migloop-search/1"
SEARCH_OR_SCHEMA = "migloop-search/2"
SEARCH_DEFAULTS: dict[str, Any] = {"q": "", "agent": None, "v": None, "since": None, "file": None,
                                    "after": False, "since_ts": None, "until_ts": None, "kind": None}
REJECT = "⛔"
Node = tuple[str, str, int | None]


def trace_identity(ledger: atoms.Ledger, calls: list[dict[str, Any]] | None,
                   metrics: dict[str, Any] | None) -> dict[str, Any]:
    """核查询轨迹身份,不读取模型 YAML 的 ledger 或结论核验状态。

    calls 是原始转录配对后的调用(text/has_result/is_error),不是 metrics 调用计数摘要。
    sessions 的身份由渲染器放在首行;只接受首个非空行的完整身份头,不在正文引用里搜索。
    任一明确提供者与当前账本不一致即拒绝绑定;没有提供者返回 None,不是匹配成功。
    """
    current = atoms.ledger_identity(ledger)
    observations: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for step, call in enumerate(calls or [], 1):
        if not isinstance(call, dict) or call.get("tool") not in ("sessions", "mcp__migloop__sessions", "search", "mcp__migloop__search"):
            continue
        text = call.get("text")
        provenance = call.get("provenance")
        reason = None
        if call.get("has_result") is not True:
            reason = "missing_result"
        elif call.get("is_error") or call.get("ok") is False or call.get("parse_error") \
                or call.get("status") in ("rejected", "error", "failed", "pending"):
            reason = "failed_or_rejected"
        elif isinstance(provenance, dict) and provenance.get("complete_pair") is False:
            reason = "unpaired_result"
        elif not isinstance(text, str):
            reason = "missing_text"
        elif text.lstrip().startswith(REJECT):
            reason = "failed_or_rejected"
        if reason:
            ignored.append({"step": step, "reason": reason})
            continue
        assert isinstance(text, str)
        if str(call.get("tool")).endswith("search"):
            receipt = search_receipt(text, call.get("input") or {})
            if receipt:
                observations.append({"identity": receipt["ledger"], "step": step, "source": "search",
                                     "search_id": receipt["id"], "call_id": call.get("call_id"), "item_id": call.get("item_id"),
                                     "result_line": call.get("result_line"), "provenance": provenance})
            continue
        first = next((line for line in text.removeprefix("\ufeff").splitlines() if line.strip()), "")
        header = re.fullmatch(r"账本身份:[ \t]+(\S+)[ \t]*", first)
        if header is None:
            ignored.append({"step": step, "reason": "missing_identity_header"})
            continue
        observations.append({"identity": header.group(1), "step": step,
                             "call_id": call.get("call_id"), "item_id": call.get("item_id"),
                             "result_line": call.get("result_line"), "provenance": provenance})
    identities = list(dict.fromkeys(row["identity"] for row in observations))
    harness = metrics.get("harness_identity") if isinstance(metrics, dict) else None
    # 空字符串没有提供身份;非字符串的显式值不能用 truthiness 吞掉,必须报冲突。
    harness_present = harness is not None and harness != ""
    harness_valid = isinstance(harness, str) and bool(re.fullmatch(r"\S+", harness))
    conflict = any(identity != current for identity in identities) or \
        (harness_present and (not harness_valid or harness != current))
    sources = [name for name in ("sessions", "search") if any(row.get("source", "sessions") == name for row in observations)]
    if harness_present:
        sources.append("harness")
    source = "+".join(sources) or None
    bound = False if conflict else True if source else None
    status = "mismatch" if conflict else "matched" if source else "legacy"
    diag = ("查询轨迹身份冲突:成功 sessions/search 返回或 harness 明示身份与当前账本不一致,不能绑定当前版本与关系。"
            if conflict else "查询轨迹身份未记录:历史调用未认证,不能据此声称当前账本身份已匹配。"
            if source is None else "查询轨迹身份匹配;只确认账本坐标所属,不验证模型缺陷主张。")
    return {"current": current, "bound": bound, "match": bound, "status": status, "source": source,
            "source_identities": identities, "harness_identity": harness,
            "observations": observations, "ignored_sessions": ignored, "diag": diag}


@dataclass
class ViaState:
    opened: list[Node] = field(default_factory=list)
    searches: dict[str, dict[str, Any]] = field(default_factory=dict)

    def has(self, node: Node) -> bool:
        return node in self.opened

    def open(self, node: Node) -> None:
        if node not in self.opened:
            self.opened.append(node)


def search_args(args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ValueError("search 参数必须是对象")
    out = {key: args.get(key, default) for key, default in SEARCH_DEFAULTS.items()}
    if args.get("q_any") is not None:
        from . import atom_queries
        normalized = atom_queries.parameters("search", {**out, "q_any": args["q_any"]})
        out = {key: normalized[key] for key in SEARCH_DEFAULTS}
        out["q_any"] = normalized["q_any"]
    return out


def search_return(ledger: atoms.Ledger, state: ViaState, args: dict[str, Any], text: str,
                  hits: list[dict[str, Any]]) -> str:
    """只给渲染器实际展示的精确命中发导航凭据;不解析片段中的自述坐标。"""
    normalized_args = search_args(args)
    multi = normalized_args.get("q_any") is not None
    token = secrets.token_hex(12)
    targets: list[dict[str, Any]] = []
    for hit in hits:
        kind, key, v = hit.get("kind"), hit.get("key"), hit.get("v")
        if kind not in ("file", "agent") or not isinstance(key, str) or type(v) is not int:
            continue
        node, _ = target(ledger, kind, key, v)
        if node != (kind, key, v):
            continue
        if multi:
            shown_terms = hit.get("matched_terms")
            if not isinstance(shown_terms, list) or not shown_terms \
                    or any(not isinstance(t, str) for t in shown_terms) \
                    or len(set(shown_terms)) != len(shown_terms) \
                    or not set(shown_terms) <= set(normalized_args["q_any"]):
                continue
        number = len(targets) + 1
        targets.append({"hit": number, "kind": kind, "key": key, "v": v, "seq": hit.get("seq"),
                        "field": hit.get("field"), "via": f"search:{token}:{number}"})
        if multi:
            targets[-1]["matched_terms"] = list(hit.get("matched_terms") or [])
    body = text + "\n搜索导航: 下列 hits 的 via 可直接打开其精确 kind/key/v;只证明本次搜索返回命中,不证明历史读取或因果。"
    receipt = {"schema": SEARCH_OR_SCHEMA if multi else SEARCH_SCHEMA, "id": token, "ledger": atoms.ledger_identity(ledger),
               "args": normalized_args, "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "hits": targets}
    state.searches[token] = receipt
    return body + "\n" + SEARCH_RECEIPT + json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))


def search_receipt(text: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """原始成功 search 返回的尾部凭据;正文引用/缺尾/参数串用均不能绑定。"""
    body, marker, footer = text.rstrip("\r\n").rpartition("\n" + SEARCH_RECEIPT)
    if not marker:
        return None
    try:
        row = json.loads(footer)
        normalized_args = search_args(args)
    except (ValueError, TypeError):
        return None
    schema = SEARCH_OR_SCHEMA if normalized_args.get("q_any") is not None else SEARCH_SCHEMA
    if not isinstance(row, dict) or row.get("schema") != schema \
            or not isinstance(row.get("id"), str) or not re.fullmatch(r"[0-9a-f]{24}", row["id"]) \
            or row.get("args") != normalized_args \
            or row.get("body_sha256") != hashlib.sha256(body.encode("utf-8")).hexdigest() \
            or not isinstance(row.get("ledger"), str) or not row["ledger"] or not isinstance(row.get("hits"), list):
        return None
    for i, hit in enumerate(row["hits"], 1):
        if not isinstance(hit, dict) or hit.get("hit") != i or hit.get("kind") not in ("file", "agent") \
                or not isinstance(hit.get("key"), str) or type(hit.get("v")) is not int or hit["v"] < 1 \
                or hit.get("via") != f"search:{row['id']}:{i}":
            return None
        if schema == SEARCH_OR_SCHEMA:
            matched = hit.get("matched_terms")
            if not isinstance(matched, list) or not matched or any(not isinstance(t, str) for t in matched) \
                    or len(set(matched)) != len(matched) or not set(matched) <= set(normalized_args["q_any"]):
                return None
    return row


def search_target(receipt: dict[str, Any], hit: int) -> Node | None:
    rows = receipt.get("hits") or []
    if hit < 1 or hit > len(rows):
        return None
    row = rows[hit - 1]
    return row["kind"], row["key"], row["v"]


def target(ledger: atoms.Ledger, kind: str, hint: str, v: int | None) -> tuple[Node | None, str | None]:
    """精确目标校验:渲染层会裁到最后一版,移动不能把这种裁剪登记成请求的版本。"""
    key = resolve_key(ledger, kind, hint)
    if key is None:
        return None, f"{REJECT} 目标不在账本: {kind}:{hint}"
    count = len(ledger.stories[key].versions) if kind == "file" else ledger.agents[key].n_versions
    if v is None or v < 1 or v > count:
        return None, f"{REJECT} 目标版本不存在: {kind}:{hint}@v{v};账本共 {count} 版,未打开。"
    return (kind, key, v), None


def returned_node(ledger: atoms.Ledger, kind: str, text: str) -> Node | None:
    """从模型收到的正文头核实际坐标;不从调用参数推定成功,正文无坐标就不能核验。"""
    lines = text.lstrip().splitlines()
    if not lines:
        return None
    if kind == "file":
        m = re.match(r"^# (?:文件 )?(.+?)\s*@v(\d+)\b", lines[0])
        if m is None:
            return None
        hint = next((ln[len("完整路径: "):] for ln in lines[1:3] if ln.startswith("完整路径: ")), m.group(1))
        return target(ledger, kind, hint, int(m.group(2)))[0]
    m = re.match(r"^# agent .*?\bid=(\S+)\s+v(\d+)\b", lines[0])
    if m is None:
        m = re.match(r"^# (\S+)\s+v(\d+)\b", lines[0])
    return target(ledger, kind, m.group(1), int(m.group(2)))[0] if m else None


def _main_agent(ledger: atoms.Ledger, sid: str) -> atoms.AgentRec | None:
    mains = [k for k in ledger.agents if k.startswith("__main__")]
    hit = [k for k in mains if k.split(":", 1)[-1].startswith(sid) or (sid and sid.startswith(k.split(":", 1)[-1]))]
    return ledger.agents[hit[0]] if len(hit) == 1 else None


def resolve_key(ledger: atoms.Ledger, kind: str, hint: str) -> str | None:
    if kind == "file":
        return filestory.find_story_path(ledger.stories, hint)
    a = atoms.resolve_agent(ledger, hint)
    if a is None and hint.startswith("__main__"):
        a = _main_agent(ledger, hint.split(":", 1)[-1])
    return a.id if a else None


def parse(ledger: atoms.Ledger, text: str) -> dict[str, Any]:
    """via 原文 → {text, first, kind, key, v, ok}。first = sessions / task 这类入口标签;坐标解析失败 ok=False。"""
    t = str(text or "").strip()
    out: dict[str, Any] = {"text": t, "first": False, "kind": None, "key": None, "v": None, "ok": False,
                           "search": None, "hit": None}
    if not t:
        return out
    search = SEARCH_RE.match(t)
    if search:
        out.update(search=search.group(1), hit=int(search.group(2)))
        return out
    low = t.lower()
    if any(low == tag or low.startswith((tag + ":", tag + " ")) for tag in FIRST_TAGS):
        out["first"] = True
        return out
    m = NODE_RE.match(t)
    if not m:
        return out
    kind, hint, vs = m.group(1), m.group(2), m.group(3)
    key = resolve_key(ledger, kind, hint)
    out.update(kind=kind, key=key, v=int(vs) if vs is not None else None)
    out["ok"] = key is not None and vs is not None          # 节点永远带版本:没版本的坐标不是合法来处
    return out


def label(ledger: atoms.Ledger, node: Node) -> str:
    kind, key, v = node
    if kind == "file":
        base = key.replace("\\", "/").rsplit("/", 1)[-1]
        return f"file:{base}" + (f"@v{v}" if v is not None else "(整个)")
    name = atoms._agent_label(ledger.agents, key) or key
    return f"agent:{name}" + (f"@v{v}" if v is not None else "(整个)")


def describe(ledger: atoms.Ledger, state: ViaState, *, exact: bool = False, limit: int | None = None) -> str:
    rows = state.opened if limit is None else state.opened[-limit:]
    names = [f"{kind}:{key}@v{v}" if exact else label(ledger, (kind, key, v)) for kind, key, v in rows]
    omitted = len(state.opened) - len(rows)
    return ("、".join(names) + (f"；另有 {omitted} 个已打开节点，原调用记录可查" if omitted else "")) \
        if names else "(还没打开任何节点)"


def check(ledger: atoms.Ledger, state: ViaState, via: str, destination: Node | None = None) -> str | None:
    """file / agent 调用前校验 via。返回 None = 放行;否则返回给模型看的错误文本(以 ⛔ 开头,调用不执行;probe 按这个前缀识别被拒)。"""
    pv = parse(ledger, via)
    opened = describe(ledger, state, exact=True, limit=8)
    if pv["search"]:
        receipt = state.searches.get(pv["search"])
        if receipt is None or receipt.get("ledger") != atoms.ledger_identity(ledger):
            return "⛔ search 来处未登记于本服务器/账本,必须照抄本次 search 返回命中的 via。"
        node = search_target(receipt, pv["hit"])
        if node is None or node != destination:
            return "⛔ search 命中与目标精确坐标不一致,不得换文件、agent 或版本。"
        return None
    if not pv["text"]:
        return ("⛔ via 缺失:file / agent 是移动,必须带 via=已打开的版本节点(file:<路径>@vN / agent:<id>@vK)。"
                f"第一次可写 via=sessions。已打开:{opened}")
    if pv["first"]:
        if state.opened:
            return f"⛔ via=sessions/task 只能用于第一次 file / agent;之后必须从已打开的节点跳。已打开:{opened}"
        return None
    if pv["key"] is not None and pv["v"] is None:
        return f"⛔ via 要带版本:{pv['text'][:80]}。节点永远是 file:<路径>@vN / agent:<id>@vK,逐字照抄你打开过的那个。已打开:{opened}"
    if not pv["ok"]:
        return f"⛔ via 解析不了或不在账本:{pv['text'][:80]}。via 必须是已打开的节点之一:{opened}"
    node: Node = (str(pv["kind"]), str(pv["key"]), pv["v"])
    if state.has(node):
        return None
    same_key = [n for n in state.opened if n[0] == node[0] and n[1] == node[1]]
    hint = f"你打开的是 {'、'.join(label(ledger, n) for n in same_key)},版本对不上。" if same_key else ""
    if not state.opened:
        hint += "当前没有已打开节点；若这是首次版本查询，请保持目标不变、改用 via=sessions 重试。本次未打开目标。"
    return f"⛔ via 不是已打开的节点:{pv['text'][:80]}。{hint}打开了什么只能从什么跳。已打开:{opened}"
