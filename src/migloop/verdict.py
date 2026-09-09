"""结构化结论:调查员报告末尾的 ``migloop-verdict/1`` 块 → 严格解析 → 节点 / 证据 / 边核回账本。

三件事分开记,互不越级:
- 模型的主张(节点、角色、原因、证据、边)原样保留,哪怕主语无效、引用核不回去;
- 检查结果另起字段:节点 ok/diag、引用 status、边 status(true / false / unknown / not_checked);
- 修复锚点(repair.before/after)不是因果角色,修复后的版本不进 roles,页面只挂「修复落点」。

节点坐标只认显式写法 ``file:<路径>@v<N>`` / ``agent:<账本 id 或唯一名字>@v<K>``(主会话 ``__main__:<会话号>``),
版本必填且在范围内;不再用正则从散文里猜主语。相邻的两个 nodes 不是事实边:每条边按账本的 写 / 读 / 派发 核,
核不出来的标 未证实,词法沾边的标 候选。
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import atoms

SCHEMA = "migloop-verdict/1"
ROLES = ("正常", "带病传递", "进入·错", "进入·缺", "无法确认")
RED = ("带病传递", "进入·错", "进入·缺")
RELATIONS = ("写", "读", "派发", "候选", "省略")
CHECK_RESULTS = ("true", "false", "unknown", "not_checked")
_TOP = {"schema", "run", "ledger", "root", "defects", "notes"}
_DEFECT = {"id", "title", "repair", "entry", "boundary", "nodes", "edges"}
_NODE = {"node", "role", "reason", "evidence", "boundary", "checks"}
_EDGE = {"from", "to", "relation", "note"}
_REPAIR = {"before", "after", "evidence"}
_CHECK = {"claim", "result"}
NODE_RE = re.compile(r"^(file|agent):(.+?)(?:@v(\d+))?$")
_FENCE = re.compile(r"```[ \t]*(yaml|yml|json|verdict)?[^\n]*\n(.*?)```", re.DOTALL)
_MAX_BLOCK_CHARS = 1_000_000
_MAX_DEPTH = 32
_MAX_ITEMS = 20_000


# ═══════════════ 抽块 / 解析 / 校验 ═══════════════

def extract_block(text: str) -> tuple[str, str] | None:
    """报告正文里最后一个带 ``migloop-verdict`` 的围栏块 → (json | yaml, 原文)。"""
    hits: list[tuple[str, str]] = []
    for m in _FENCE.finditer(text or ""):
        body = m.group(2)
        if "migloop-verdict" in body:
            hits.append((m.group(1) or "", body))
    if not hits:
        return None
    kind, body = hits[-1]
    if not kind:
        kind = "json" if body.lstrip().startswith("{") else "yaml"
    return ("json" if kind == "json" else "yaml"), body


def _no_dup(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"重复键: {k}")
        out[k] = v
    return out


def _structure_error(data: Any) -> str | None:
    pending = [(data, 0)]
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > _MAX_DEPTH or count > _MAX_ITEMS:
            return "结论块嵌套过深或项目过多"
        if isinstance(value, dict):
            if any(not isinstance(k, str) for k in value):
                return "映射键必须是字符串"
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
    return None


def parse_block(kind: str, raw: str) -> tuple[Any, list[str]]:
    """安全解析;重复键、语法错误都报出来,不猜。YAML 需要 PyYAML(没有就只收 JSON)。"""
    if len(raw) > _MAX_BLOCK_CHARS:
        return None, [f"结论块过大(最多 {_MAX_BLOCK_CHARS} 字符)"]
    if kind == "json":
        try:
            data = json.loads(raw, object_pairs_hook=_no_dup)
            error = _structure_error(data)
            return (None, [error]) if error else (data, [])
        except (ValueError, RecursionError) as e:
            return None, [f"JSON 解析失败: {e}"]
    try:
        import yaml
    except ImportError:
        return None, ["需要 PyYAML 才能解析 YAML 块;改输出 JSON"]

    class _Strict(yaml.SafeLoader):
        def __init__(self, stream: str) -> None:
            super().__init__(stream)
            self.verdict_depth = 0
            self.verdict_items = 0

        def compose_node(self, parent: Any, index: Any) -> Any:
            if self.check_event(yaml.AliasEvent):
                raise yaml.YAMLError("结论块不允许 YAML 别名")
            self.verdict_depth += 1
            self.verdict_items += 1
            if self.verdict_depth > _MAX_DEPTH or self.verdict_items > _MAX_ITEMS:
                raise yaml.YAMLError("结论块嵌套过深或项目过多")
            try:
                return super().compose_node(parent, index)
            finally:
                self.verdict_depth -= 1

    def _mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for k_node, _v in node.value:
            key = loader.construct_object(k_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(None, None, "映射键必须是字符串", k_node.start_mark)
            if key in seen:
                raise yaml.constructor.ConstructorError(None, None, f"重复键: {key}", k_node.start_mark)
            seen.add(key)
        return dict(yaml.SafeLoader.construct_mapping(loader, node, deep))

    _Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                            lambda loader, node: _mapping(loader, node, True))
    try:
        return yaml.load(raw, Loader=_Strict), []
    except (yaml.YAMLError, RecursionError) as e:
        return None, [f"YAML 解析失败: {str(e).splitlines()[0] if str(e) else e}"]


def _is_str(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _check_keys(obj: dict[str, Any], allowed: set[str], where: str, errs: list[str]) -> None:
    if any(not isinstance(k, str) for k in obj):
        errs.append(f"{where}: 映射键必须是字符串")
    extra = sorted(k for k in obj if isinstance(k, str) and k not in allowed)
    if extra:
        errs.append(f"{where}: 未知键 {', '.join(extra)}")


def _check_node_spec(x: Any, where: str, errs: list[str]) -> None:
    if not _is_str(x):
        errs.append(f"{where}: node 必须是 file:<路径>@v<N> / agent:<id>@v<K> 字符串")
    else:
        match = NODE_RE.match(x.strip())
        if match is None:
            errs.append(f"{where}: 坐标格式不对 {x!r}")
        elif match.group(3) is None:
            errs.append(f"{where}: 缺版本号(@v<N>)")


def validate(data: Any) -> list[str]:
    """严格 schema:未知键、类型不对、词表外的角色 / 关系 / 检查结果都算错。"""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是映射"]
    structure_error = _structure_error(data)
    if structure_error:
        return [structure_error]
    _check_keys(data, _TOP, "顶层", errs)
    if data.get("schema") != SCHEMA:
        errs.append(f"schema 必须是 {SCHEMA}(现在是 {data.get('schema')!r})")
    for k in ("run", "ledger", "root", "notes"):
        if k in data and data[k] is not None and not isinstance(data[k], str):
            errs.append(f"{k} 必须是字符串")
    if "root" in data and data["root"] is not None:
        _check_node_spec(data["root"], "root", errs)
    defects = data.get("defects")
    if not isinstance(defects, list):
        errs.append("defects 必须是列表")
        return errs
    ids: set[str] = set()
    for i, d in enumerate(defects):
        w = f"defects[{i}]"
        if not isinstance(d, dict):
            errs.append(f"{w}: 必须是映射")
            continue
        _check_keys(d, _DEFECT, w, errs)
        did = d.get("id")
        if not _is_str(did):
            errs.append(f"{w}: 缺 id")
        elif did in ids:
            errs.append(f"{w}: 缺陷 id 重复 {did}")
        else:
            ids.add(str(did))
        if not _is_str(d.get("title")):
            errs.append(f"{w}: 缺 title")
        if "boundary" in d and d["boundary"] is not None and not isinstance(d["boundary"], str):
            errs.append(f"{w}: boundary 必须是字符串")
        rep = d.get("repair")
        if rep is not None:
            if not isinstance(rep, dict):
                errs.append(f"{w}.repair: 必须是映射")
            else:
                _check_keys(rep, _REPAIR, f"{w}.repair", errs)
                for k in ("before", "after"):
                    if rep.get(k) is not None:
                        _check_node_spec(rep[k], f"{w}.repair.{k}", errs)
                if rep.get("evidence") is not None and not (isinstance(rep["evidence"], list)
                                                            and all(isinstance(x, str) for x in rep["evidence"])):
                    errs.append(f"{w}.repair.evidence 必须是字符串列表")
        ent = d.get("entry")
        if ent is not None:
            if not isinstance(ent, list):
                errs.append(f"{w}.entry 必须是列表")
            else:
                for j, x in enumerate(ent):
                    _check_node_spec(x, f"{w}.entry[{j}]", errs)
        nodes = d.get("nodes")
        if not isinstance(nodes, list):
            errs.append(f"{w}: nodes 必须是列表")
            nodes = []
        for j, n in enumerate(nodes):
            wn = f"{w}.nodes[{j}]"
            if not isinstance(n, dict):
                errs.append(f"{wn}: 必须是映射")
                continue
            _check_keys(n, _NODE, wn, errs)
            _check_node_spec(n.get("node"), wn, errs)
            if n.get("role") not in ROLES:
                errs.append(f"{wn}: role 必须是 {' / '.join(ROLES)} 之一(现在是 {n.get('role')!r})")
            if not _is_str(n.get("reason")):
                errs.append(f"{wn}: 缺 reason")
            if n.get("evidence") is not None and not (isinstance(n["evidence"], list)
                                                      and all(isinstance(x, str) for x in n["evidence"])):
                errs.append(f"{wn}: evidence 必须是字符串列表")
            if n.get("boundary") is not None and not isinstance(n["boundary"], str):
                errs.append(f"{wn}: boundary 必须是字符串")
            checks = n.get("checks")
            if checks is not None:
                if not isinstance(checks, list):
                    errs.append(f"{wn}: checks 必须是列表")
                else:
                    for ci, c in enumerate(checks):
                        if not isinstance(c, dict):
                            errs.append(f"{wn}.checks[{ci}]: 必须是映射")
                            continue
                        _check_keys(c, _CHECK, f"{wn}.checks[{ci}]", errs)
                        if not _is_str(c.get("claim")):
                            errs.append(f"{wn}.checks[{ci}]: 缺 claim")
                        if c.get("result", "not_checked") not in CHECK_RESULTS:
                            errs.append(f"{wn}.checks[{ci}]: result 必须是 {' / '.join(CHECK_RESULTS)} 之一")
        edges = d.get("edges")
        if edges is not None:
            if not isinstance(edges, list):
                errs.append(f"{w}: edges 必须是列表")
                edges = []
            for j, e in enumerate(edges):
                we = f"{w}.edges[{j}]"
                if not isinstance(e, dict):
                    errs.append(f"{we}: 必须是映射")
                    continue
                _check_keys(e, _EDGE, we, errs)
                _check_node_spec(e.get("from"), f"{we}.from", errs)
                _check_node_spec(e.get("to"), f"{we}.to", errs)
                if e.get("relation") is not None and e["relation"] not in RELATIONS:
                    errs.append(f"{we}: relation 必须是 {' / '.join(RELATIONS)} 之一(现在是 {e.get('relation')!r})")
                if e.get("note") is not None and not isinstance(e["note"], str):
                    errs.append(f"{we}: note 必须是字符串")
    return errs


def load_block(text: str) -> dict[str, Any]:
    """报告正文 → {found, kind, raw, data, errors}:抽块、解析、校验一步到位;任何一步失败都保留原文与错误。"""
    blk = extract_block(text)
    if blk is None:
        return {"found": False, "kind": None, "raw": None, "data": None, "errors": ["报告里没有 migloop-verdict/1 结论块"]}
    kind, raw = blk
    data, errs = parse_block(kind, raw)
    if data is not None:
        errs = validate(data)
    return {"found": True, "kind": kind, "raw": raw, "data": data if not errs else None, "errors": errs}


def repair_prompt(lb: dict[str, Any]) -> str:
    """一次 schema 修复重试的提示:只让模型重发结论块,不许再调查。"""
    why = "\n".join(f"- {e}" for e in lb.get("errors") or ["缺结论块"])
    return ("你上一条回复末尾的结构化结论块(schema: migloop-verdict/1)无法载入:\n" + why +
            "\n\n请只重新输出一个完整的 ```yaml 围栏块(guide 里「结构化结论」一节的格式),内容与你已得出的结论一致;"
            "不要再调用工具,不要输出别的文字。")


# ═══════════════ 节点 / 证据 / 边核回账本 ═══════════════

def _main_agent(ledger: atoms.Ledger, sid: str) -> atoms.AgentRec | None:
    if not sid:
        return None
    mains = [k for k in ledger.agents if k.startswith("__main__")]
    hit = [k for k in mains if k.split(":", 1)[-1].startswith(sid) or (sid and sid.startswith(k.split(":", 1)[-1]))]
    return ledger.agents[hit[0]] if len(hit) == 1 else None


def _agent(ledger: atoms.Ledger, hint: str) -> atoms.AgentRec | None:
    a = atoms.resolve_agent(ledger, hint)
    if a is None and hint.startswith("__main__"):
        a = _main_agent(ledger, hint.split(":", 1)[-1])
    return a


def _n_versions(ledger: atoms.Ledger, kind: str, key: str) -> int:
    if kind == "file":
        return len(ledger.stories[key].versions)
    return sum(1 for act in ledger.agents[key].actions if act.ver is not None)


def resolve_node(ledger: atoms.Ledger, spec: Any) -> dict[str, Any]:
    """显式坐标 → {spec, kind, key, v, ok, diag, label}。主语无效只给 diag,key 留空,不猜别的节点。"""
    out: dict[str, Any] = {"spec": str(spec), "kind": None, "key": None, "v": None, "ok": False, "diag": None,
                           "label": str(spec)}
    m = NODE_RE.match(str(spec).strip()) if spec is not None else None
    if not m:
        out["diag"] = "坐标格式不对(file:<路径>@v<N> / agent:<id>@v<K>)"
        return out
    kind, hint, vs = m.group(1), m.group(2).strip(), m.group(3)
    out["kind"] = kind
    if kind == "file":
        normalized = hint.replace("\\", "/")
        exact = [p for p in ledger.stories if p.replace("\\", "/") == normalized]
        suffix = "/" + normalized.lstrip("/")
        absolute = normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized)
        candidates = exact if absolute else exact or [p for p in ledger.stories if p.replace("\\", "/").endswith(suffix)]
        if len(candidates) > 1:
            out["diag"] = f"文件坐标有歧义({len(candidates)} 个匹配): {hint};请使用完整路径"
            return out
        if not candidates:
            out["diag"] = f"文件不在账本: {hint}"
            return out
        key = candidates[0]
        label = key.replace("\\", "/").rsplit("/", 1)[-1]
    else:
        a = _agent(ledger, hint)
        if a is None:
            out["diag"] = f"agent 不在账本: {hint}"
            return out
        key = a.id
        label = a.name or a.id
    if vs is None:
        out["diag"] = "缺版本号(@v<N>)"
        out["label"] = label
        return out
    if len(vs.lstrip("0")) > 12:
        out["diag"] = "版本越界"
        return out
    v = int(vs.lstrip("0") or "0")
    n = _n_versions(ledger, kind, key)
    out["v"] = v
    out["label"] = f"{label}@v{v}" if kind == "file" else f"{label} v{v}"
    if v < 1 or v > n:
        out["diag"] = f"版本越界(1..{n})"
        return out
    out["key"] = key
    out["ok"] = True
    return out


def _seq_owner(ledger: atoms.Ledger, seq_no: int) -> tuple[str | None, int | None]:
    for a in ledger.agents.values():
        for act in a.actions:
            if act.seq == seq_no:
                return a.id, act.ver if act.ver is not None else act.at
    return None, None


def resolve_evidence(ledger: atoms.Ledger, ev: Any) -> dict[str, Any]:
    """一条证据 → 动作引用(status 按 resolve_ref)/ 节点坐标 / 解析不了的文字。有效只说明位置可核,不背书 reason。"""
    s = str(ev).strip()
    m = atoms.REF_RE.search(s)
    if m:
        tag = m.group(1) or m.group(5)
        try:
            no, line = int(m.group(2)), int(m.group(3))
            block = int(m.group(4)) if m.group(4) is not None else None
        except ValueError:
            return {"ref": s, "type": "action", "status": "invalid", "seq": None, "aid": None, "v": None,
                    "diag": "动作引用数字超出解析范围"}
        hit, status = atoms.resolve_ref(ledger, no, line, block, tag)
        out: dict[str, Any] = {"ref": s, "type": "action", "status": status, "seq": hit, "aid": None, "v": None}
        if hit is not None:
            out["aid"], out["v"] = _seq_owner(ledger, hit)
        return out
    if NODE_RE.match(s):
        n = resolve_node(ledger, s)
        return {"ref": s, "type": "node", "status": "ok" if n["ok"] else "invalid", "node": n}
    return {"ref": s, "type": "text", "status": "unparsed"}


def _rel_write(ledger: atoms.Ledger, ag: dict[str, Any], fl: dict[str, Any]) -> tuple[str, str]:
    ver = ledger.stories[fl["key"]].versions[fl["v"] - 1]
    if ver.by != ag["key"]:
        return "false", f"v{fl['v']} 的写者是 {ver.by}" + (f" v{ver.by_ver}" if ver.by_ver is not None else "")
    if ver.by_ver == ag["v"]:
        return "true", f"写于 agent v{ver.by_ver}" + (f"(#{ver.act_seq})" if ver.act_seq else "")
    return "false", f"是它写的,但写者版本是 v{ver.by_ver},不是 v{ag['v']}"


def _rel_read(ledger: atoms.Ledger, fl: dict[str, Any], ag: dict[str, Any]) -> tuple[str, str]:
    a = ledger.agents[ag["key"]]
    best, note = "false", "账本里没有它读这一版的记录"
    for act in a.actions:
        feed = act.ver if act.ver is not None else act.at
        if feed > ag["v"]:
            continue
        for ref in act.files:
            if ref.op != "read" or ref.path != fl["key"] or ref.v != fl["v"]:
                continue
            if ref.certain and not ref.ev.dep:
                return "true", f"#{act.seq} 读到 v{fl['v']},喂 v{feed}"
            best, note = "unknown", f"#{act.seq} 读了它但版本是就近绑定或依赖读(内容未进上下文)"
        if best == "false" and fl["key"] in (act.detail.get("conditional_reads") or []):
            best, note = "unknown", f"#{act.seq} 条件分支里提到,是否读到未知"
    return best, note


def _rel_dispatch(ledger: atoms.Ledger, parent: dict[str, Any], child: dict[str, Any]) -> tuple[str, str]:
    c = ledger.agents[child["key"]]
    if c.parent != parent["key"]:
        return "false", f"{child['key']} 的派发者是 {c.parent or '无'}"
    if c.parent_ver == parent["v"]:
        return "true", f"派发于父 v{c.parent_ver}"
    return "false", f"是它派发的,但派发时在 v{c.parent_ver},不是 v{parent['v']}"


def _rel(ledger: atoms.Ledger, a: dict[str, Any], b: dict[str, Any], rel: str) -> tuple[str, str] | None:
    """一种关系在这两个端点上核一遍;端点种类对不上这种关系时返回 None。方向按关系语义:写 agent→file,读 file→agent,派发 父→子。"""
    if rel == "写" and a["kind"] == "agent" and b["kind"] == "file":
        return _rel_write(ledger, a, b)
    if rel == "读" and a["kind"] == "file" and b["kind"] == "agent":
        return _rel_read(ledger, a, b)
    if rel == "派发" and a["kind"] == "agent" and b["kind"] == "agent":
        return _rel_dispatch(ledger, a, b)
    return None


def _candidate(ledger: atoms.Ledger, a: dict[str, Any], b: dict[str, Any]) -> str | None:
    ag, fl = (a, b) if a["kind"] == "agent" else (b, a)
    if ag["kind"] != "agent" or fl["kind"] != "file":
        return None
    for m in ledger.mentions.get(fl["key"], []):
        if m.by == ag["key"] and m.by_ver == ag["v"]:
            return f"词法沾边({m.cls}):{m.ctx[:60]}"
    return None


def check_edge(ledger: atoms.Ledger, a: dict[str, Any], b: dict[str, Any],
               relation: str | None) -> tuple[str, str, str]:
    """一条边 → (status, 关系, 说明)。status: true(账本有这条边)/ false(核过,没有)/ unknown(候选)/ not_checked(端点无效)。
    给了关系词只核那一种;没给或写 候选 / 省略 就把 写 / 读 / 派发 都试一遍,再看词法候选。"""
    if not (a.get("ok") and b.get("ok")):
        return "not_checked", relation or "", "端点无效,没核"
    rels = [relation] if relation in ("写", "读", "派发") else ["写", "读", "派发"]
    last = "两端种类对不上这种关系"
    unknown: tuple[str, str] | None = None
    for r in rels:
        got = _rel(ledger, a, b, r)
        if got is None:
            continue
        st, note = got
        if st == "true":
            return "true", r, note
        if st == "unknown" and unknown is None:
            unknown = (r, note)
        last = note
    if unknown:
        return "unknown", unknown[0], unknown[1]
    if relation in ("写", "读", "派发"):
        return "false", relation, last
    cand = _candidate(ledger, a, b)
    if cand:
        return "unknown", "候选", cand
    return "false", "未证实", "账本里没有这两个节点之间的写 / 读 / 派发边"


def _norm_checks(checks: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for c in checks or []:
        out.append({"claim": str(c.get("claim") or ""), "result": str(c.get("result") or "not_checked"),
                    "source": "model"})
    return out


def build(ledger: atoms.Ledger, data: dict[str, Any] | None, errors: list[str],
          meta: dict[str, Any]) -> dict[str, Any]:
    """校验过的块 → 页面载荷:defects(节点 / 边 / 修复锚点各带核验结果)+ roles(按 键 → [(缺陷, 版本, 角色)] 摊平,
    只收主语有效的节点)+ fixed(修复落点)。errors 非空时 data 为 None,只回原文与错误。"""
    cur = atoms.ledger_identity(ledger)
    model = (data or {}).get("ledger") or None
    harness = meta.get("harness_identity") or None
    conflict = any(x != cur for x in (model, harness) if x is not None)
    bound = bool(model and not conflict)
    status = "mismatch" if conflict else "matched" if bound else "missing"
    diag = ("账本身份不匹配,原始主张未绑定当前账本" if conflict else
            "模型未记录账本身份,原始主张未绑定当前账本" if not bound else None)
    out: dict[str, Any] = {
        "schema": (data or {}).get("schema"), "kind": meta.get("kind"), "raw": meta.get("raw"),
        "errors": list(errors), "repaired": bool(meta.get("repaired")),
        "identity": {"current": cur, "claimed": model or harness, "model": model, "harness": harness,
                     "match": False if conflict else True if bound else None,
                     "bound": bound, "status": status, "diag": diag},
        "root": None, "defects": [], "roles": {}, "fixed": [], "notes": (data or {}).get("notes"),
    }
    if data is None:
        return out

    def node(spec: Any) -> dict[str, Any]:
        if bound:
            return resolve_node(ledger, spec)
        return {"spec": str(spec), "kind": None, "key": None, "v": None, "ok": False,
                "diag": diag, "label": str(spec)}

    def evidence(ref: Any) -> dict[str, Any]:
        if bound:
            return resolve_evidence(ledger, ref)
        return {"ref": str(ref), "type": "text", "status": "not_checked", "diag": diag}

    if data.get("root"):
        out["root"] = node(data["root"])
    roles: dict[str, list[dict[str, Any]]] = {}
    for d in data.get("defects") or []:
        did = str(d.get("id"))
        rep = d.get("repair") or {}
        before = node(rep["before"]) if rep.get("before") else None
        after = node(rep["after"]) if rep.get("after") else None
        rep_ev = [evidence(x) for x in rep.get("evidence") or []]
        entries = [node(x) for x in d.get("entry") or []]
        entry_keys = {(e["kind"], e["key"], e["v"]) for e in entries if e["ok"]}
        nodes: list[dict[str, Any]] = []
        for n in d.get("nodes") or []:
            r = node(n.get("node"))
            ev = [evidence(x) for x in n.get("evidence") or []]
            role = str(n.get("role"))
            if (r["ok"] and after and after["ok"] and role in RED
                    and (r["kind"], r["key"], r["v"]) == (after["kind"], after["key"], after["v"])):
                r["ok"] = False
                r["diag"] = "修复后的版本是修复落点(repair.after),不能标带病;修复后是否还有问题另标"
            row = {**r, "role": role, "reason": str(n.get("reason") or ""), "evidence": ev,
                   "evidence_bad": sum(1 for x in ev if x["status"] not in ("ok", "drifted")),
                   "boundary": n.get("boundary"), "checks": _norm_checks(n.get("checks")),
                   "entry": (r["kind"], r["key"], r["v"]) in entry_keys, "defect": did,
                   "checked": "not_checked"}
            nodes.append(row)
            if r["ok"]:
                roles.setdefault(str(r["key"]), []).append(row)
        edges: list[dict[str, Any]] = []
        explicit: set[tuple[str, str]] = set()
        for e in d.get("edges") or []:
            fa, fb = node(e.get("from")), node(e.get("to"))
            st, rel, note = check_edge(ledger, fa, fb, e.get("relation"))
            edges.append({"from": fa, "to": fb, "relation": rel, "claimed": e.get("relation"), "status": st,
                          "note": note, "implicit": False, "model_note": e.get("note")})
            explicit.add((fa["spec"], fb["spec"]))
        for x, y in zip(nodes, nodes[1:]):
            if (x["spec"], y["spec"]) in explicit or (y["spec"], x["spec"]) in explicit:
                continue
            st, rel, note = check_edge(ledger, x, y, None)
            if st == "not_checked":
                continue
            edges.append({"from": {k: x[k] for k in ("spec", "kind", "key", "v", "ok", "diag", "label")},
                          "to": {k: y[k] for k in ("spec", "kind", "key", "v", "ok", "diag", "label")},
                          "relation": rel, "claimed": None, "status": st, "note": note, "implicit": True,
                          "model_note": None})
        if after and after["ok"]:
            out["fixed"].append({"defect": did, "kind": after["kind"], "key": after["key"], "v": after["v"]})
        out["defects"].append({"id": did, "title": str(d.get("title") or ""), "boundary": d.get("boundary"),
                               "repair": {"before": before, "after": after, "evidence": rep_ev},
                               "entry": entries, "nodes": nodes, "edges": edges})
    out["roles"] = roles
    return out
