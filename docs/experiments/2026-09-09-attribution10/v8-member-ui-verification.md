# V8 Member real-run UI verification

2026-09-09. Completed run `formal-v8/member-center/runs/tools/rep1`; both investigator and viewer are frozen **b540cb2**. Page: port **19674**, session `ff019d8a`. This is a separate actual V8 result, not the [V7 alternative-viewer replay](v8-alternative-viewer-ui.md). No model was invoked by this audit; source, pool, task and original-run inventories remain unchanged.

Result: projection, source identity, raw-document and diagnostic-display checks pass. One non-blocking action-click scope issue was independently reproduced and is preserved below. Machine assertions and source-record hashes are in [the JSON audit](v8-member-ui-verification.json).

## Actual behavior

- 38 MCP call records; 18 `action(ref)` calls. Each returned the requested exact citation and actual action number. Seventeen matched an original tool-use ID; one `say` action matched the source physical line and original text instead of inventing a tool ID.
- Four tail actions (#16/#23/#24/#26) correctly retain their real owner/action pointer with `v=null`; no agent v41/v4 is created. All 18 action calls remain outside `trajectory.visits` and `transitions`.
- 2 opened and 3 rejected version requests; 8 original trajectory nodes. Four explicit, ledger-supported model write edges have empty `query_steps`. Three additional display-only endpoints are unqueried; no model step or blue visit is manufactured.
- The single search entrance (#35) remains in the separate navigation timeline and is not a read edge. All four graph arrows preserve exact agent/file direction and version. No read edge is drawn.
- Eight node reasons and both basis blocks/reference lists match the original `verdict.yaml` exactly. Findings retain 1 file grouping / 3 items, including S3 as an unassociated item because the final document supplies no repair anchor. Its reasons/references remain present, not attached to root by inference.
- Initial fit, widths 1250/2200/1600 and candidate toggles preserve non-overlapping boxes entirely inside the viewport. There is no real expansion stub in this graph, so no real stub claim is made. The original run-file inventory and process/graph snapshots remain unchanged through these checks. Both standard real-page helpers pass without JavaScript exceptions.

## Real new check feedback is not semantic clearance

The submitted reference selects check **#38**, call `call_3jFfuAh5rvL8a2vMjtAyWAbo`. Original-document SHA-256 is `a2eacaa702e45d5ce94e7d29c6d879729b3a500dc6b61fdcb0c2ff8b2f37d7c6`; canonical document SHA-256 is `d3eff5c2ef999c6f2b7978fc0b6d1c974d0bf8d5b927150aa6b67e646329935c`. `checked_draft_ref` is verified/accepted and `draft_check=matched` means this same document was checked—not that it cleared all diagnostics.

The raw native check responses are at transcript **L203 (#37)** and **L212 (#38)**. Every returned issue and status matches the rendered check history. #37 has 5 issues. The final #38 is still **needs_review**, with **4 warnings**, not `mechanical_clear`:

- S4_PRICE: a cited action occurs after the stated agent-v12 anchor.
- S4_COMPILE: one cited action occurs after v40 and is in tail feeding slot 41, and another cited action also occurs after the anchor.

The current consistency panel contains these same four code/node/message warnings and preserves `semantic_checked=false`; the earlier draft's invalid-node/role diagnostics remain expandable in its historical record. Both basis fields and warnings coexist without changing model role text. Coverage is 38/38 accounted with **21 deferred/unconfirmed** records; neither this nor document matching certifies factual completeness or causal accuracy.

## Preserved UI issue: clicking an action may change viewing scope

Actual V8 step **#16** uses `ref=#a68daf720e780b4c2:15731@L592`. Its parsed node correctly has `{aid: agent-a68daf720e780b4c2, action: 15731, v: null}`. However, the step row is clickable and passes that node to `openProbeNode`; its fallback calls `openRoot` with `v=null`.

A real click therefore left evidence projection mode and changed the displayed root to the whole agent (`anchorVer=null`) instead of opening the cited action's input/output. The original trajectory stayed unchanged and no fake v41 was introduced, but the human's requested viewing scope was not preserved. The same generic action-step route should be corrected for all action calls, not only tails: open the authentic action record without rerooting, and make unlocatable action steps non-navigable. No frozen source or run was modified to hide this finding; any fixed-viewer replay must be recorded separately.

## New screenshots

- [Real V8 graph and original visit statuses](screenshots/v8-real-member-reference-rep1-geometry.png)
- [Original basis plus expandable real check diagnostics](screenshots/v8-member-reference-rep1-basis.png)
- [Basic graph/edge smoke](screenshots/v8-member-reference-rep1-trace.png)

The geometry and basis screenshots were visually inspected. The checked source/pool/task digests match the b540cb2 case manifest. This audit makes no assertion about the correctness of the model's underlying causal explanations.
