# V8 viewer replay of the unchanged V7 runs

2026-09-09. Read-only real-browser audit of completed `formal-v7/{codex-c4,member-center}/runs/tools/rep1`. Investigator source remains **84bfcf8**; alternative viewer is **b540cb2**, on ports 19673/19674. This is not a new investigation and is not a V8 model result. No model was called and no production, frozen-source, pool, or original-run file was changed.

Result: both real pages pass the new projection/reference contract. Full details, original action-line hashes and browser assertions are in [the JSON audit](v8-alternative-viewer-ui.json).

| Observed | C4 | Member |
|---|---:|---:|
| Original MCP call records | 75 | 56 |
| Opened / rejected version requests | 6 / 3 | 3 / 2 |
| Original trajectory nodes | 7 | 8 |
| Additional model-selected, unqueried display endpoints | 0 | 2 |
| Original navigation transitions | 5 | 2 |
| Model-selected, ledger-supported write edges | 1 | 2 |
| Query steps attached to those new edges | 0 | 0 |
| Original reasons compared exactly | 4 | 9 |
| Original basis blocks compared exactly | 0 (absent) | 2 |
| Current viewer boundary warnings | 0 | 2 |

There are no read edges. Search entrances remain independent navigation events, not fabricated reads. The three new write arrows preserve their declared agent-to-file direction, explicitly mark model selection separately from ledger evidence, and have empty `query_steps`. `complete=false` still means this is not the full ledger or a complete root-cause graph. A located write does not certify the model's causal explanation.

## What was checked

Both standard real-page helpers passed. An independent check compared all 131 call rows and their physical transcript call/result IDs; every original `trajectory` object was equal to the old viewer's object. Original arguments, scopes, call IDs, timings and provenance also match; derived `steps.node` has the corrections listed below. Browser interaction did not change any probe process/graph snapshot. Run-file inventories remained identical before and after interaction.

Original `verdict.yaml` bytes/text, canonical document hashes, 13 reasons and both available basis blocks/references remain unchanged. Both submissions remain `checked_draft_ref`, verified and accepted from the same run's recorded check call. C4's missing basis is reported as missing, not synthesized. The last checks still match at C4 #75 and Member #56.

Each projected write's original input/result record was read back, with the matching explicit tool-call ID and target filename; hashes are recorded in JSON:

- C4: `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` L8066/L8068, `call_sOYpciVhfgk1glebywbIbHAY`, agent v249 → LaunchAgreementDialog v1.
- Member: `agent-af0e3d2ae54dbf769.jsonl` L32/L33 and L34/L35, `toolu_01W4Yg3nfX75u3Yxsk1X4wat` and `toolu_01YcRVJymkRf9wtm51Pr5qt8`, agent v2 → MemberCenterPage v15 and agent v3 → file v16.

Member's new agent v2/file v15 endpoints are gray, `traj=false`, `opened=[]`, and have no blue visited badge or query step. Clicking both opened the actual atom drawers; their exact-version `scope_only=1` requests completed with HTTP 200 without creating visits or transitions. Initial fit, widths 1250/2200/1600, candidate toggles and endpoint drawer interactions all retained non-overlapping boxes entirely inside the graph viewport. Neither real graph has a ledger stub to expand; that behavior is not claimed as a real-page test here.

C4 remains **0 file associations / 1 unassociated item**: no repair endpoint or root association was invented. Its authentic action reference `#01a009fe-68e3-7f42-b76b-5e863c555976:2375@L7997` opened through the original action endpoint with HTTP 200. It is no longer labeled a historical unbound reference; the rendered original fragment was 485 characters. This click changed no graph/visit/repair data.

## Current warnings are not historical check responses

Member now shows two `ledger_boundary`, `semantic_checked=false` warnings under current declaration checks: `S4_PRICE` cites `#a68daf720e780b4c2:15670@L501`; `S4_COMPILE` cites `#af0e3d2ae54dbf769:17286@L23`. Both diagnose a post-anchor action boundary, not an automatic causal error. Their complete JSON is expandable in the current consistency panel.

The entire historical `draft_check` object still equals the 84bfcf8 viewer's object. Earlier C4 #74's conflicting-role warning and Member #55's wrong-writer/invalid-node errors remain available; final #75/#56 still return their original `mechanical_clear` status. The newly computed boundary warnings were not inserted into those old returns or represented as feedback the investigator had seen. Member still accounts for 38/38 records with 19 deferred/unconfirmed items; this is not semantic clearance.

## Deliberate derived-node differences

Twenty action rows have corrected derived coordinates, while original call records and full navigation remain unchanged:

- C4 #5–9 now have `node=null`. Their original responses at transcript L60–63 and L75 explicitly say `没有这个动作`; the old viewer incorrectly guessed agent v249 from a transcript UUID or `#UUID`. The new page shows neutral rows such as `#5 action · 原文 #2387 input · 0.1千字`, class `st na`, with no node links and no “success/opened/evidence seen” claim. The call-count tooltip explicitly includes failed/unreturned calls. A minor limitation remains: these rows do not expand the missing-action return inline.
- C4 #20/21/25–29 drop the nonexistent tail effect v250 to `v=null`.
- Member #24/25/26/35/39/40/46/47 similarly drop tail slots v41 or v4 to `v=null` while preserving the real owner/action pointer.

These are viewer-derived coordinate corrections, not changes to the original model's calls or reports.

## Source integrity and screenshots

Recomputed viewer source inventory: 47 files, digest `008bb634b4c614dd480ecdd632f3ae3679e41147dff78160f45631cbe59ad981`. Both original 84bfcf8 source inventories and both shared-pool inventories match their original case manifests. Ledger identities naturally match; no identity override was used.

- [C4 new model-source arrow and actual root drawer](screenshots/v8-alt-b540cb2-v7-c4-reference-rep1-geometry.png)
- [Member two model-source arrows and gray endpoints](screenshots/v8-alt-b540cb2-v7-member-reference-rep1-geometry.png)
- [Member endpoint drawer after both scope responses, with current boundary warning](screenshots/v8-alt-b540cb2-scope-ready-v7-member-reference-rep1-geometry.png)
- [C4 preserved check diagnostics](screenshots/v8-alt-b540cb2-v7-c4-basis.png)
- [Member actual model basis and preserved check diagnostics](screenshots/v8-alt-b540cb2-v7-member-basis.png)

The intermediate `v8-alt-b540cb2-endpoints-v7-member-reference-rep1-geometry.png` is preserved too: it was captured before the asynchronous scope-only response. The separate scope-ready screenshot above is the completed-state evidence; no screenshot was overwritten. Four screenshots were visually inspected, and all browser passes reported no JavaScript exceptions.

V8 Member rep1 was still `starting` in its metrics during this audit. No unfinished report was judged. New V8 outcomes belong in a separate result file after completion.
