# V7 real UI verification

2026-09-09. Investigator and viewer both use frozen `84bfcf8`; this is not an alternative-source replay. Only completed `formal-v7/{codex-c4,member-center}/runs/tools/rep1` reference submissions were judged. New UI servers are C4 `19671` and Member `19672`; existing services were not replaced. No production, frozen-source, pool or original-run file was edited, and no model was invoked for this audit.

## Results

| Measure | C4 | Member |
| --- | --- | --- |
| MCP steps / host wrappers | 75 / 0 | 56 / 0 |
| Version requests | 9: 6 opened, 3 rejected | 5: 3 opened, 2 rejected |
| Exact graph nodes | 7 | 8 |
| Search records | 27 | 11 |
| Recorded transitions | 5 search entries | 1 search entry, 1 same-node navigation |
| Main read/write graph edges | 0 | 0 |
| Original reasons compared | 4 | 9 |
| Original basis blocks compared | 0, honestly absent | 2 |
| Final check | #75 matched | #56 matched |
| Findings | 0 files, 1 retained unassociated item | 1 file, 3 items |

Both existing real-page helpers (`probe_smoke.cjs`, `probe_basis_smoke.cjs`) passed. A further browser check compared original `verdict.yaml` bytes/text, every reason and available basis field/reference, all step rows, per-item finding causes, and physical transcript call/result IDs. All 131 steps have matching explicit `call_id` at their recorded physical lines and verified migloop origin. All six search navigation credentials returned before the subsequent navigation request. Four check events create no version visits. No unfinished or unverified version request was observed; the five rejected requests remain rejected, not silently opened.

The original call/step/trajectory/evidence snapshots and each original run's complete file-name/SHA256 map were unchanged after browser interaction. The two full canonical-session atom URLs loaded with HTTP 200, and the actual root drawers completed, not merely their reason overlays. No JavaScript exception was observed.

### Geometry

Actual rectangles were checked at 1900×1300, then 1250×1300, 2200×1300 and 1600×1300, with candidate display both on and off. All atom/stub boxes were non-overlapping and inside the fitted canvas viewport. Both actual graphs have **no ledger stub**, so this audit does not claim a real stub-expansion pass. Findings and reason expansion, candidate toggling, root-drawer loading and resize were exercised without altering the recorded process.

### Document and check provenance

Both sources are `checked_draft_ref`, accepted with matching ledger/model/harness identity and `semantic_checked=false`:

- C4 document hash `dbb21269d11f918e3e998d524b1a4ec96d3d05e0f5e0db93d5582e5fe503f319`; raw/draft hash `1e05d3eab8dc3173b9d3714d0d0db2d498231f9643f3ef8f9be6b648dea93147`; source check #75, `call_sOFoSKQGH284gc6FCfclQ5J9`.
- Member document hash `2b06f5856c937d7f8a9aaac17a7cce08482678ce61c3482abc330216b940ac25`; raw/draft hash `999a69648fc6873d561817e1f0b6084119d80cb81678b783d37b754fef2dafd5`; source check #56, `call_4UP9IGw8m9zxr1EjcdrEZ5tw`.

Earlier diagnostics remain expandable: C4 #74's role-conflict warning; Member #55's wrong writer edge and invalid agent node. Final mechanical clearance does not erase these earlier drafts. C4 coverage 0/0 is an empty recorded denominator, not exhaustive repair truth. Member accounts for 38/38 records but still has 19 deferred/unconfirmed records; the UI preserves the distinction and semantic disclaimer.

## Conditional-read version boundary

The actual main graphs contain no invented version read edge: search entries are excluded as search, and Member's page revisit is excluded as a self-navigation. Since these two investigations did not repeat the old problematic v16→agent-v5/v33 navigation, an additional **separate current-ledger regression** loaded frozen 84bfcf8 against the Member pool and checked file v16 against agent `agent-a68daf720e780b4c2` at v5, v33 and v40.

All three return `relation_status=unknown`, `relation_kind=候选`, and null causal endpoints, with path-level conditional evidence still visible. Thus the prior future-version read is not emitted as a version-specific read relation. This was not a replay or rebinding of an old model investigation. Loading and checking took 11.58 s in a fresh process. The result and per-step raw physical locators are retained in [the JSON audit](v7-ui-verification.json).

## Issues and honest limitations

### 1. Missing repair association incorrectly disables current references

C4 supplies no `repair.before/after`. `findings.project` correctly retains its item under `unbound_items` and does not invent a root association. However, `renderFindings` passes `false` as the item's reference-binding flag merely because there is no file bucket. It labels all 13 already locatable references as “历史引用未绑定 · ok” and disables navigation, even though the document and ledger identity are current and authenticated.

This conflates **unassociated repair file** with **unbound historical document/reference**. The original reasons are not lost, and canonical node drawers still work. A future UI fix should split those flags: keep the item unassociated, allow authenticated current raw references, and never invent repair endpoints. Reported to the parent; no template change was made.

Relevant paths: `findings.py:71–90`; `fixchain.html` `renderFindings` / `appendItem`, especially the unbound group and `canBind` evidence branch.

### 2. Explicit checked model relations are outside the current projection

C4's submitted document includes one mechanically true write edge, and Member's includes two. The current graph scope is only `recorded_transitions`; these edges are omitted because the investigator did not navigate those endpoint pairs via a corresponding declared transfer. The resulting zero-edge graphs faithfully implement the current scope, but are narrower than the model's explicitly declared, mechanically checked relation set.

This does not justify turning search navigation into a read/write relation. It motivates a separate graph source, described below. Neither zero edges nor mechanical `true` certifies causal correctness.

## Next-source evaluation: checked explicit model edges (not implemented)

The existing SVG geometry and read/write styles are reusable, but the data contract and source labels need a small explicit extension:

1. In `probe_payload`, after `_structured` and the recorded-transition projection, process only the document's explicit `edges` (`implicit=false`). Gate this new source on authenticated/current document provenance and matching identity. A bad final document must not erase independently authenticated query edges.
2. Validate each endpoint exactly, preserve the declared direction, and resolve supporting ledger actions in that same direction. For a first bounded implementation, admit mechanically true read/write relations only. Path candidates, unbound read versions, lexical mentions, dispatch, implicit adjacency and false relations remain diagnostics. Do not use the reverse-direction convenience selection of `_relation_check` to certify a differently directed model declaration.
3. Locate the actual write/read action and original source lines; for reads also require the version-bound observation and appropriate execution/delivery proof. A locatable path mention is not a read of the queried version. No all-pairs scan is needed: work is proportional to explicit declarations, with per-agent support indexes if needed.
4. Preserve separate provenance axes, e.g. `selection_source=checked_model_edge`, `source_of_claim=model`, `verification_source=ledger_raw_action`, plus document hash, defect ID and declaration index. Keep query-derived records separately as `recorded_transition`. Deduplicate equal physical relations while retaining both provenance lists and per-defect declarations.
5. Model-only edges have `query_steps=[]`; never invent a step number or mutate `trajectory.visits/transitions/searches`. Current `fixchain.html:2105–2115` rejects non-`ledger` sources, and `2452–2501` always renders `#steps` and “来源：账本原始动作；转移 #...”; these branches must handle the explicit new source and absence of query steps. The corresponding browser helper currently assumes every edge has a first step and also needs adjustment.
6. Endpoint display needs an explicit choice. C4's true edge endpoints are already displayed, so it can reuse those nodes. Member's v15/agent-v2 true write endpoints are absent from current trajectory nodes. Either initially exclude such edges with an honest `endpoint_not_displayed` diagnostic, or add separate exact **unqueried claim endpoint** layout records without changing the original trajectory; gray/unvisited status must remain. Do not silently expand all neighboring ledger nodes.

Keep `complete=false` with scope such as `recorded_transitions + checked_explicit_declarations`, not “full causal graph”. Required regressions include unbound/mismatched source, explicit-vs-implicit distinction, wrong-direction declarations, path-only candidates, model-only edges with no query step, repeated declarations across defects, missing displayed endpoints and unchanged original process hashes.

## New screenshots

- [C4 trace](screenshots/v7-c4-reference-rep1-trace.png), [C4 check details](screenshots/v7-c4-reference-rep1-basis.png), [C4 after resize and drawer completion](screenshots/v7-c4-reference-rep1-geometry.png).
- [Member trace](screenshots/v7-member-reference-rep1-trace.png), [Member check/basis](screenshots/v7-member-reference-rep1-basis.png), [Member after resize and drawer completion](screenshots/v7-member-reference-rep1-geometry.png).

The two geometry screenshots and two check/basis screenshots were visually inspected. The debugging skill's source/observation separation guided this audit; migloop has no GitNexus index, so the work used frozen source, raw transcript locations and actual browser/API behavior without creating an index.
