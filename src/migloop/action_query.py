"""Exact action addresses for all query transports and recorded-step projection.

A transcript tag is not an agent ID. Callers may copy the located citation
instead; this reuses the ledger's location resolver, never guessing ownership.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import atoms


@dataclass(frozen=True)
class Address:
    agent: str
    seq: int
    requested_ref: str | None = None
    status: str = "legacy_id_seq"
    requested_id: str | None = None


def resolve(ledger: atoms.Ledger, *, id: str | None = None, seq: int | None = None,
            ref: str | None = None) -> Address:
    """Resolve one complete citation or one explicit owner/sequence pair.

    Legacy nonexistent coordinates remain a normal missing-action response.
    Reference ambiguity/missing identity is an error, not a seq-only fallback.
    """
    if ref is None:
        if not isinstance(id, str) or not id.strip() or type(seq) is not int:
            raise ValueError("action 需要 ref=完整原文引用，或同时给 id 和 seq")
        owner = atoms.resolve_agent(ledger, id)
        if owner is None:
            return Address(id, seq, status="missing_owner", requested_id=id)
        return Address(owner.id, seq, status="legacy_id_seq" if id == owner.id else "legacy_alias", requested_id=id)
    if id is not None or seq is not None:
        raise ValueError("action 的 ref 与 id/seq 必须二选一")
    if not isinstance(ref, str) or not (match := atoms.REF_RE.fullmatch(ref.strip())):
        raise ValueError("action.ref 必须是单个完整引用 #转录标识:n@L行[/块]，不接受正文或文件节点")
    tag = match[1] or match[5]
    try:
        number, line = int(match[2]), int(match[3])
        block = int(match[4]) if match[4] is not None else None
    except ValueError as exc:
        raise ValueError("action.ref 数字超出解析范围") from exc
    if number < 1 or line < 1:
        raise ValueError("action.ref 的动作号和行号必须大于0")
    hit, status = atoms.resolve_ref(ledger, number, line, block, tag)
    if hit is None or status not in ("ok", "drifted"):
        raise ValueError(f"action.ref 无法唯一定位: {status}；不得仅按 #n 猜测")
    owners = [(agent.id, act) for agent in ledger.agents.values()
              for act in agent.actions if act.seq == hit]
    if len(owners) != 1:
        raise ValueError("action.ref 的动作归属缺失或歧义")
    aid, act = owners[0]
    if act.src is None or type(act.src[1]) is not int or act.src[1] < 0:
        raise ValueError("action.ref 没有原始记录指针")
    resolved_tag, ambiguous = atoms.resolve_tag(ledger, tag or "")
    if (ambiguous or ledger.tag_paths.get(resolved_tag) != act.src[0]
            or act.src[1] + 1 != line or block is not None and act.blk != block):
        raise ValueError("action.ref 与原始记录指针不一致")
    return Address(aid, hit, ref.strip(), status)


def step(ledger: atoms.Ledger, address: Address) -> dict | None:
    """An action is not a node visit; never invent a tail effect version."""
    owner = ledger.agents.get(address.agent)
    if owner is None:
        return None
    matches = [act for act in owner.actions if act.seq == address.seq]
    if len(matches) != 1:
        return None
    act = matches[0]
    feeding = act.ver if act.ver is not None else act.at
    version = feeding if type(feeding) is int and 1 <= feeding <= owner.n_versions else None
    return {"kind": "agent", "aid": owner.id, "v": version, "action": act.seq}
