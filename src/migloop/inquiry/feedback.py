"""Diagnostic projections shared by MCP and the card audit; never add edges."""

def related_evidence(graph):
    # Retain the persisted graph field for old cards; it never meant a required
    # causal handoff. Expose actual operation times, not just opaque scopes.
    return {
        "required": False,
        "operations": [
            {k: row.get(k) for k in ("link", "op", "agent", "path", "at", "strength", "request", "result")}
            for row in graph["missing_evidence_links"]
        ],
        "note": "Optional already-cited operations, not missing required edges or suggested paths. A later read may be a readback, not input to an earlier write. Do not add it merely to remove this list.",
    }


def time_conflict(upstream, downstream):
    def operation(event):
        return {k: event[k] for k in ("id", "relation", "evidence", "at")}
    return {"code": "time_reversal", "upstream": operation(upstream),
            "downstream": operation(downstream),
            "note": "This branch uses a later operation as input to an earlier one. Expanding cutoffs or force does not reorder events. If this indexed operation is not the claimed handoff, find its actual earlier input (including script-internal reads) and resubmit that connection with relation + original evidence, without force. An unresolved result can then authorize a reviewed force in the next revision. Do not retain a known-wrong readback just because its individual edge binds. Other branches may fail for different reasons."}
