"""Host-recorded analysis identity, separate from historical migration models."""
import copy
import os
from pathlib import Path

from .common import load, strings, write_new

ALLOWED = {"models", "platforms", "root_session_ids"}


def labels(value):
    if not isinstance(value, dict) or set(value) - ALLOWED:
        raise ValueError("Analysis labels allow models, platforms and root_session_ids only")
    result = {}
    for key, values in value.items():
        strings(values, "analysis." + key)
        if values:
            result[key] = sorted(set(values))
    return result


def from_host(metadata):
    """Opt-in host context; never guess the analyst from the investigated pool."""
    path = os.environ.get("MIGLOOP_ANALYSIS_CONTEXT")
    if not path:
        return {}
    context = load(path)
    if context.get("schema") != "migloop-analysis-runtime/1":
        raise ValueError("Unsupported host analysis context")
    if Path(context.get("materials", "")).resolve() != Path(metadata["materials"]).resolve():
        raise ValueError("Host analysis context belongs to another material pool")
    return labels(context.get("analysis", {}))


def record_analysis(memory, records, base_revision):
    """Annotate known analysis labels only; rebind identical claims, not lessons."""
    from .registry import revision_of, validate_case
    from .card_contract import require_valid_card
    from .case_format import content, claims
    if not isinstance(records, dict) or not records:
        raise ValueError("Supply case-ID to recorded analysis labels mapping")
    with memory.lock():
        state = memory._base(base_revision)
        prepared = []
        for identity, values in records.items():
            values = labels(values)
            if not values.get("models"):
                raise ValueError("Observed analysis models required for " + identity)
            old = memory.case(identity, state=state)
            require_valid_card(old)
            if old["schema"] != "migloop-case/4":
                raise ValueError("Compact legacy cards before recording analysis labels")
            new = copy.deepcopy(old)
            analysis = new["metadata"].setdefault("analysis", {})
            for key, value in values.items():
                if key in analysis and analysis[key] and sorted(set(analysis[key])) != value:
                    raise ValueError("Conflicting recorded analysis." + key + " for " + identity)
                analysis[key] = value
            new["revision"] = revision_of(new)
            validate_case(new)
            assert content(new) == content(old) and claims(new) == claims(old)
            if new["revision"] != old["revision"]:
                prepared.append((old, new))
        if not prepared:
            return {"revision": state["revision"], "annotated": 0, "rebound": 0}
        revisions = {old["id"]: (old["revision"], new["revision"]) for old, new in prepared}
        rebound = 0
        for lesson in state["lessons"].values():
            for ref in lesson["evidence"]:
                previous = revisions.get(ref["case"])
                if previous and ref["revision"] == previous[0]:
                    ref["revision"] = previous[1]
                    rebound += 1
        for old, new in prepared:
            path = memory.root / "cases" / new["id"] / (new["revision"] + ".json")
            if path.exists():
                if load(path) != new:
                    raise ValueError("Existing annotated card differs from expected content")
            else:
                write_new(path, new)
            # Preserve withdrawn status/claims; this is not a semantic re-admission.
            state["cases"][new["id"]]["revision"] = new["revision"]
        result = memory._publish(state, [{"analysis_labels_recorded": sorted(revisions),
                                          "identical_claim_bindings_rebound": rebound}])
        return {**result, "annotated": len(prepared), "rebound": rebound}
