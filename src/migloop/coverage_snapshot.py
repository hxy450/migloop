"""Select a harness-recorded repair denominator without reapplying a newer candidate policy.

Only the caller may supply verdict.json's top-level repair_manifest here; model YAML
is not a source for this snapshot. Validation binds coordinates/events, not repair truth.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

from . import atoms

SCHEMA = "migloop-repair-manifest/1"
MAX_TARGETS = 20_000


def select_manifest(ledger: atoms.Ledger, current_manifest: dict[str, Any],
                    recorded_manifest: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an independent manifest copy plus an explicit binding/policy diagnostic.

    Invalid recorded data never silently switches to a complete new denominator:
    errors also enter the returned manifest's errors consumed by coverage.reconcile.
    """
    current_policy = current_manifest.get("policy", "legacy")
    origin: dict[str, Any] = {"source": "current", "status": "runtime_manifest_unrecorded",
                              "bound": True, "policy": current_policy, "current_policy": current_policy,
                              "policy_changed": False, "manifest_errors": [],
                              "semantic_checked": False}
    identity = atoms.ledger_identity(ledger)
    if recorded_manifest is None:
        origin["bound"] = current_manifest.get("ledger") == identity and not current_manifest.get("errors")
        return deepcopy(current_manifest), origin

    errors: list[dict[str, Any]] = []

    def issue(code: str, **details: Any) -> None:
        errors.append({"code": "recorded_manifest_" + code, **details})

    if not isinstance(recorded_manifest, dict):
        issue("invalid_shape", message="harness repair_manifest 必须是对象")
        recorded: dict[str, Any] = {}
    else:
        recorded = recorded_manifest
    policy = recorded.get("policy", "legacy")
    origin.update(policy=policy, policy_changed=policy != current_policy)
    if not isinstance(policy, str) or not policy.strip():
        issue("invalid_policy")
    if recorded.get("schema") != SCHEMA:
        issue("unsupported_schema")
    if recorded.get("ledger") != identity:
        issue("ledger_mismatch")
    path = current_manifest.get("file")
    if not isinstance(path, str) or path not in ledger.stories or recorded.get("file") != path:
        issue("file_mismatch")
        story = None
    else:
        story = ledger.stories[path]
    if not isinstance(recorded.get("errors", []), list) or recorded.get("errors"):
        issue("has_errors", message="记录的清单本身含错误")

    items, candidates = recorded.get("items"), recorded.get("candidates")
    if not isinstance(items, list) or not isinstance(candidates, list):
        issue("invalid_targets", message="items 和 candidates 必须是列表")
        items, candidates = [], []
    if len(items) + len(candidates) > MAX_TARGETS:
        issue("too_many_targets", limit=MAX_TARGETS)
        items, candidates = [], []
    versions = {version.v: version for version in story.versions} if story else {}
    seen_nodes: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issue("invalid_item", item=index)
            continue
        v, node = item.get("v"), item.get("node")
        if type(v) is not int or v not in versions or node != f"file:{path}@v{v}":
            issue("invalid_version", item=index)
            continue
        if node in seen_nodes:
            issue("duplicate_node", item=index, node=node)
        seen_nodes.add(node)
        if "before" in item and item["before"] != (f"file:{path}@v{v - 1}" if v - 1 in versions else None):
            issue("invalid_before", item=index)
        version = versions[v]
        event = item.get("event")
        if event is not None:
            expected = atoms.event_id(ledger, version.by, version.act_seq) if version.act_seq is not None else None
            if not isinstance(event, dict) or (event.get("id") is not None and event.get("id") != expected):
                issue("invalid_version_event", item=index)

    seen_candidates: set[str] = set()
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            issue("invalid_candidate", candidate=index)
            continue
        aid, seq, eid, cid = item.get("agent"), item.get("seq"), item.get("event_id"), item.get("id")
        if not isinstance(path, str) or path not in ledger.stories \
                or not isinstance(aid, str) or aid not in ledger.agents or type(seq) is not int \
                or not isinstance(eid, str) or not eid or item.get("file") != path:
            issue("invalid_candidate", candidate=index)
            continue
        # This checks the recorded event, not whether today's policy still selects it.
        actual = atoms.event_id(ledger, aid, seq)
        if actual is None or actual != eid:
            issue("invalid_candidate_event", candidate=index)
            continue
        expected_id = "candidate:" + hashlib.sha256((eid + "\0" + path).encode("utf-8")).hexdigest()[:20]
        if not isinstance(cid, str) or cid != expected_id:
            issue("invalid_candidate_id", candidate=index)
        elif cid in seen_candidates:
            issue("duplicate_candidate", candidate=index, id=cid)
        else:
            seen_candidates.add(cid)
        event = item.get("event")
        if event is not None and (not isinstance(event, dict) or event.get("id") != eid):
            issue("invalid_candidate_event", candidate=index)
        if item.get("writer_confirmed", False) is not False or item.get("repair_confirmed", False) is not False:
            issue("candidate_claims_fact", candidate=index)

    if errors:
        selected = deepcopy(current_manifest)
        selected["errors"] = list(selected.get("errors") or []) + errors
        origin.update(source="invalid", status="invalid_recorded_manifest", bound=False, manifest_errors=errors)
        return selected, origin
    origin.update(source="recorded", status="matched")
    return deepcopy(recorded), origin
