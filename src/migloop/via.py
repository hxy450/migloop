"""来处(via):模型任一时刻站在一个节点上,只能从已打开的节点跳。

节点只有两种:file(path[, v]) 打开的文件节点、agent(id[, v]) 打开的 agent 节点;打开索引(不带 v)时节点就是「整个」,
via 必须逐字对上打开它时的样子 —— 打开了什么,只能从什么跳。blame / diff / action / search 不移动、不开节点。
第一次 file / agent 允许 via=sessions / task(从返修链摘要进来),之后不允许。校验在服务端做:不对就不执行。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import atoms, filestory

NODE_RE = re.compile(r"^(file|agent):(\S+?)(?:@v(\d+))?(?=\s|$)")
FIRST_TAGS = ("sessions", "task")
REJECT = "⛔"
Node = tuple[str, str, int | None]


@dataclass
class ViaState:
    opened: list[Node] = field(default_factory=list)

    def has(self, node: Node) -> bool:
        return node in self.opened

    def open(self, node: Node) -> None:
        if node not in self.opened:
            self.opened.append(node)


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
    out: dict[str, Any] = {"text": t, "first": False, "kind": None, "key": None, "v": None, "ok": False}
    if not t:
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
    out["ok"] = key is not None
    return out


def label(ledger: atoms.Ledger, node: Node) -> str:
    kind, key, v = node
    if kind == "file":
        base = key.replace("\\", "/").rsplit("/", 1)[-1]
        return f"file:{base}" + (f"@v{v}" if v is not None else "(整个)")
    name = atoms._agent_label(ledger.agents, key) or key
    return f"agent:{name}" + (f"@v{v}" if v is not None else "(整个)")


def describe(ledger: atoms.Ledger, state: ViaState) -> str:
    return "、".join(label(ledger, n) for n in state.opened) or "(还没打开任何节点)"


def check(ledger: atoms.Ledger, state: ViaState, via: str) -> str | None:
    """file / agent 调用前校验 via。返回 None = 放行;否则返回给模型看的错误文本(以 ⛔ 开头,调用不执行;probe 按这个前缀识别被拒)。"""
    pv = parse(ledger, via)
    opened = describe(ledger, state)
    if not pv["text"]:
        return ("⛔ via 缺失:file / agent 是移动,必须带 via=你现在站的节点(已打开的那个,逐字照抄:打开索引时不带版本,"
                f"打开某一版时带 @vN)。第一次可写 via=sessions。已打开:{opened}")
    if pv["first"]:
        if state.opened:
            return f"⛔ via=sessions/task 只能用于第一次 file / agent;之后必须从已打开的节点跳。已打开:{opened}"
        return None
    if not pv["ok"]:
        return f"⛔ via 解析不了或不在账本:{pv['text'][:80]}。via 必须是已打开的节点之一:{opened}"
    node: Node = (str(pv["kind"]), str(pv["key"]), pv["v"])
    if state.has(node):
        return None
    same_key = [n for n in state.opened if n[0] == node[0] and n[1] == node[1]]
    hint = ""
    if same_key and node[2] is not None and any(n[2] is None for n in same_key):
        hint = f"你打开的是它的索引(整个),没打开 v{node[2]};要从 v{node[2]} 出发先 file/agent(…, v={node[2]}),或者 via 不带版本。"
    elif same_key:
        hint = f"你打开的是 {'、'.join(label(ledger, n) for n in same_key)},版本对不上。"
    return f"⛔ via 不是已打开的节点:{pv['text'][:80]}。{hint}打开了什么只能从什么跳。已打开:{opened}"
