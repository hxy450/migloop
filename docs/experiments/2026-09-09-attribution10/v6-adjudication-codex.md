# V6 C4 document/reference adjudication

Scope: four tool-assisted developer-set runs for C4_dialog_hit_test_patch_boundary, all GPT-5.5/medium/native on source 4d5db4f, the same frozen C4 task/pool, and reference-v1/codex-reference.json. This is an independent read of the reports and raw R1/R2 evidence. Mechanical check/submission acceptance is assessed separately from semantic truth. There is no raw arm in this report, so it does not support an overall raw-versus-tools efficacy claim.

## Raw evidence boundary

- R1 rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl: the user reports that the page is stuck and consent has no response (physical L7997); source output exposes the event handlers and visible-state HitTestMode.Block (L8026-L8027); SDK output says Default permits self and children while Block blocks children (L8047-L8048 and L8051-L8052); the actual patch changes only Block to Default (L8066-L8067), and readback shows Default (L8109-L8110). The R1 close says .migbot/config.json blocked CLI validation, no new HAP was produced, and the existing HAP predated the patch (L8115).
- R2 rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl: native output shows a later HAP rebuild, BUILD SUCCESSFUL, successful bundle installation, and HAP installed (L840-L841). This proves a later same-project build/install, not that this exact source line was in that HAP.
- R2 native commands read saved walk/manifest artifacts. The walk ledger records consent leading into Guide (L1073-L1074), and the later checkpoint/manifest records a click at the button bounds followed by GuideStatusFragment (L3758-L3759). These are stored operational records, not this investigator independently replaying the click, inspecting the referenced screenshot/dump, or binding behavior to the patch.
- Later judge material marks the page fail/elements-missing for visual/text findings and does not close reject/link behavior (L4426-L4430). That does not prove the hit-test defect persists. No source/HAP hash, exact target-line snapshot at build time, or A/B device result binds the patch to the later package or transition. “不同意” and both agreement links remain behaviorally unverified.

## Per-run adjudication

### document rep1

Core: **accepted**. It correctly identifies the user symptom, source line, SDK semantics, exact patch/readback, and the R1 no-new-HAP boundary.

Full annotation: **incomplete but recoverable**. It does not open R2’s native build/install output or saved walk manifest. Instead it opens later assistant/final statements at #4912/#4920/#4929 and carefully labels build/install as a claim. It says no consent transition was found in the records it expanded, which is scoped and not globally false, but omits directly available R2 evidence. No false patch-to-device causal binding is asserted.

Delivery: inline YAML accepted. The first check found two invalid references and a duplicate-node role conflict; a second check is mechanically clear and matches the final document. semantic_checked=false.

### document rep2

Core: **accepted**. It opens the R1 source/SDK/patch/readback and R2 native build/install. It explicitly refuses to bind the later HAP to the patch without a target snapshot/hash.

Full annotation: **accepted with minor wording caution**. It opens both the saved walk-ledger and manifest route, calls them principally tool/ledger records, notes that links were scope-exited, and says later visual fail/elements-missing neither disproves the patch nor completes behavior verification. The notes’ shorthand that runtime “能点击…进入” is slightly stronger than an independent replay, but the immediately surrounding evidence-layer caveat makes the intended boundary clear.

Delivery: inline YAML accepted; one check is mechanically clear and matches the final document. semantic_checked=false.

### reference rep1

Core: **accepted**. It recovers the complete static chain, R1 immediate verification failure, and direct R2 native build/install. It does not invent the former agent@v253 node and does not bind the later HAP to the patch.

Full annotation: **requires a small evidence-level downgrade**. It actually opens the native command reading the saved checkpoint/manifest and discloses that some later evidence comes from report/manifest and child claims. However, it then summarizes this as advancing to “设备 UI 上可点击…并越过” the gate. The supported formulation is that a saved later manifest records one click-to-Guide transition; no independent replay or patch-bound behavior proof occurred. This is not a core-cause error because the report also states the causal boundary.

Delivery: the final response is a migloop-verdict-ref/1; the sole full check is mechanically clear, and submission authenticates the last draft and exact materialized verdict.yaml with both hashes and the current ledger. semantic_checked=false.

### reference rep2

Core: **accepted**. It correctly separates the strong static near-cause, exact patch/readback, R1 no-new-HAP result, R2 native build/install, and missing patch/artifact binding.

Full annotation: **accepted**. It describes the later click evidence as a walk/manifest report layer rather than an independently expanded raw touch log or pixel review, retains the visual-fail and untested-interaction boundaries, and avoids claiming four-click closure or sole runtime causation.

Delivery: the first check reports only a duplicate-role warning; the corrected second draft is mechanically clear. The final reference binds that last complete draft and its materialized YAML by ledger and two hashes. semantic_checked=false.

## Cost and route observations

| mode | rep | input total | cache read | uncached input | output | tool calls | tool-return chars | result chars | wall | end-to-end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| document | 1 | 1,879,723 | 1,686,016 | 193,707 | 15,180 | 62 | 389,622 | 3,560 | 324.684 s | 327.360 s |
| document | 2 | 976,936 | 856,576 | 120,360 | 12,725 | 51 | 202,196 | 4,288 | 275.466 s | 278.129 s |
| reference | 1 | 1,715,048 | 1,581,056 | 133,992 | 12,788 | 76 | 240,574 | 269 | 284.256 s | 286.900 s |
| reference | 2 | 856,826 | 749,568 | 107,258 | 11,721 | 44 | 177,468 | 269 | 250.494 s | 253.162 s |

Across these two repetitions, reference mode is lower in both repetitions for input, uncached input, output, wall, and end-to-end time. Using arm totals, the observed changes are about −10.0% input total, −23.2% uncached input, −12.2% output, −10.9% wall, and −10.8% end-to-end. Final response characters fall from 7,848 to 538 in aggregate, but reference mode still generates the full checked draft: checked-draft characters are 12,204 versus 11,486 for document mode. Tool calls increase from 113 to 120 in aggregate while tool-return characters fall from 591,818 to 418,042. Thus neither call count nor final-response length alone explains token/time movement.

These are four tools-only developer observations, not an end-to-end efficacy result. Investigation paths and semantic coverage differ across repetitions, the set is a reused development case, currency cost is NULL, and input_total already includes cache reads. A separate same-pool raw comparison is required before making raw-versus-tools or 20–30% token-reduction claims.

## Bottom line

All four runs preserve the C4 core fact pattern. Full annotations are mixed: document rep1 materially omits stronger later evidence; reference rep1 slightly upgrades a stored manifest record; document rep2 and reference rep2 maintain the important evidence boundary. Both output modes deliver parseable, matched artifacts, but mechanical acceptance never certifies the causal or behavioral claims.
