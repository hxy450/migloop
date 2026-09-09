"""Read-only projections of agent atoms at an authenticated invocation cutoff.

This is a disclosure boundary, not a new ledger state or a historical replay.
Deferred coordinates describe later records, never completed effects at cutoff.
"""
from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from . import time_scope

if TYPE_CHECKING:
    from .atoms import Action, FileRef, Ledger


_MESSAGES = frozenset({"say", "think", "inbox", "instruction", "inject", "system", "notify", "interrupt", "compact"})
_INPUT_DETAIL = frozenset({"cmd", "args", "pattern", "path", "url", "name", "description",
                           "subagent_type", "model", "prompt", "to", "recipient", "skill"})
_EFFECTS = frozenset({"write", "delete", "dispatch", "message"})


def agent_until(ledger: Ledger, payload: dict[str, Any], until: int) -> dict[str, Any]:
    """Copy an agent atom, withholding results unavailable at ``until`` use time.

    Missing/ambiguous/late cutoffs raise ValueError rather than returning an
    apparently bounded full payload. The caller may still query action originals
    or remove until. No transcript is read and neither argument is modified.
    """
    if type(until) is not int or until < 0 or not isinstance(payload, dict):
        raise ValueError("until 必须唯一定位该 agent 的实际调用，不能使用未知截止")
    scope = time_scope.for_atom(ledger, "agent", payload, until=until)
    anchor = scope["anchor"]
    if anchor.get("status") != "valid" or not anchor.get("time"):
        raise ValueError(str(anchor.get("reason") or "until 时间锚点未知"))
    cutoff_time = time_scope._time(anchor["time"])
    owner = ledger.agents[payload["id"]]
    by_seq: dict[int, Action] = {}
    for act in owner.actions:
        if act.seq in by_seq:
            raise ValueError("agent 动作号不唯一，不能安全截断")
        by_seq[act.seq] = act
    cutoff_action = by_seq[until]
    out = deepcopy(payload)
    for name in ("actions", "reads", "writes", "children", "inbox"):
        if not isinstance(out.get(name), list) or any(not isinstance(r, dict) for r in out[name]):
            raise ValueError(f"agent {name} 不是有效记录列表")
    metadata: dict[str, Any] = {
        "seq": until, "use_ts": anchor["time"], "anchor": deepcopy(anchor),
        "excluded": {}, "deferred_reads": [], "deferred_effects": [],
        "scope_note": "仅披露截止调用发起时已可用的输入；延后/未知结果不算当时已读，效应不算当时完成。"
                      "排除项仍可用 action(id, seq) 或去掉 until 查看，非不存在证明。",
    }
    out["cutoff"] = metadata
    out["time_scope"] = scope

    def allowed(act: Action) -> bool:
        use = time_scope._time(act.ts)
        return act.seq <= until and (use is None or use <= cutoff_time)

    def state(act: Action, done_ts: Any = None) -> str:
        use = time_scope._time(act.ts)
        if use is None:
            return "unknown"
        if act.kind in _MESSAGES and (act.src is None or act.src[1] == act.src[2]):
            if use == cutoff_time and act is not cutoff_action:
                left, right = act.src, cutoff_action.src
                if not (left and right and left[0] == right[0]
                        and (left[1], act.blk) < (right[1], cutoff_action.blk)):
                    return "unknown"
            return "observed"
        done = time_scope._time(done_ts if done_ts is not None else act.done_ts)
        if done is None or done < use:
            return "unknown"
        if done > cutoff_time:
            return "pending"
        if done == cutoff_time:
            # Millisecond equality alone cannot prove a result preceded a call.
            left, right = act.src, cutoff_action.src
            if not (left and right and left[0] == right[0] and left[2] is not None
                    and left[2] < right[1]):
                return "unknown"
        return "completed"

    def actual(row: dict[str, Any]) -> Action:
        seq = row.get("seq")
        if type(seq) is not int or seq not in by_seq:
            raise ValueError("载荷动作不能唯一定位到该 agent，不能安全截断")
        return by_seq[seq]

    def pointer(act: Action) -> dict[str, Any]:
        return {"agent": owner.id, "seq": act.seq, "source": list(act.src) if act.src else None,
                "use_ts": act.ts, "done_ts": act.done_ts}

    deferred: set[tuple] = set()

    def read_ref(row: dict[str, Any], act: Action) -> FileRef | None:
        matches = [r for r in act.files if r.op == "read" and r.path == row.get("path")
                   and r.v == row.get("v") and r.ev.via == row.get("via")
                   and r.ev.start == row.get("start") and r.ev.n == row.get("n")]
        return matches[0] if len(matches) == 1 else None

    def project_read(row: dict[str, Any], act: Action) -> dict[str, Any] | None:
        ref = read_ref(row, act)
        if not allowed(act):
            return None
        use = time_scope._time(act.ts)
        completion = state(act, ref.ev.done_ts if ref else None)
        if ref and use is not None and ref.ev.via == "inject" and completion == "observed":
            row.update(availability_basis="input", completion_state=completion)
            return row
        dependency = ref and ref.ev.dep and ref.ev.via not in ("image", "stdout")
        if dependency and use is not None:
            # A command names an input dependency; that does not prove it was
            # read successfully or that its contents entered model context.
            row.update(availability_basis="dependency", completion_state=completion, seen=None, full=False)
            if completion not in ("completed", "observed"):
                row.update(v=None, certain=False, latest_v=None, stale=False)
            return row
        if ref and completion in ("completed", "observed"):
            row.update(availability_basis="result", completion_state=completion)
            return row
        key = (act.seq, row.get("path"), row.get("v"), row.get("start"), row.get("n"))
        if key not in deferred:
            deferred.add(key)
            metadata["deferred_reads"].append({**pointer(act), "path": row.get("path"), "v": row.get("v"),
                "reason": "截止时结果尚未返回" if completion == "pending" else "读的完成时间/来源无法核验"})
        return None

    actions = []
    completed: set[int] = set()
    for row in out["actions"]:
        act = actual(row)
        if not allowed(act):
            continue
        completion = state(act)
        row.update(completion_state=completion, use_ts=act.ts, done_ts=act.done_ts,
                   source=list(act.src) if act.src else None)
        files = []
        for file in row.get("files") or []:
            if file.get("op") == "read":
                item = project_read(file, act)
                if item is not None:
                    files.append(item)
            elif completion in ("completed", "observed"):
                files.append(file)
        row["files"] = files
        if completion in ("completed", "observed"):
            completed.add(act.seq)
        else:
            row["ok"] = None
            keys = _INPUT_DETAIL | ({"text", "summary"} if act.kind == "message" else set())
            row["detail"] = {k: value for k, value in row.get("detail", {}).items() if k in keys} \
                            if time_scope._time(act.ts) is not None else {}
            if act.kind in _EFFECTS:
                metadata["deferred_effects"].append({**pointer(act), "kind": act.kind,
                    "recorded_v": act.ver, "completion_state": completion,
                    "reason": "效应完成在截止之后或时刻未知；此窗口只记录调用/候选，不认证完成"})
        actions.append(row)
    out["actions"] = actions
    out["reads"] = [item for row in out["reads"]
                    if (item := project_read(row, actual(row))) is not None]
    out["inbox"] = [row for row in out["inbox"]
                    if allowed(actual(row)) and state(actual(row)) in ("completed", "observed")]
    # These two derived collections lack seq in older atom payloads. Match only
    # exact recorded effects, never infer ownership from a path or timestamp alone.
    write_keys = {(ref.path, ref.v, ref.op, act.ver, ref.ev.ts)
                  for act in owner.actions if act.seq in completed
                  for ref in act.files if ref.op != "read"}
    out["writes"] = [row for row in out["writes"]
                     if (row.get("path"), row.get("v"), row.get("op"), row.get("ver"), row.get("ts")) in write_keys]
    child_keys = {(act.detail.get("child"), act.ver) for act in owner.actions
                  if act.seq in completed and act.kind == "dispatch"}
    out["children"] = [row for row in out["children"] if (row.get("id"), row.get("ver")) in child_keys]
    # Aggregate result has no per-item provenance. It is never earlier input;
    # explicit in-window message actions remain available with their own pointers.
    out["result"] = None
    metadata["excluded"] = {name: len(payload[name]) - len(out[name])
                            for name in ("actions", "reads", "writes", "children", "inbox")}
    metadata["excluded"]["result"] = int(bool(payload.get("result")))
    return out
