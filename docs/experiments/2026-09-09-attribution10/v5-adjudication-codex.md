# Formal-v5 C4 adjudication

Run: `_migloop-eval-20260909/attribution10/formal-v5/codex-c4/runs/tools/rep1`, frozen source `5b770be`; actual model/effort/transport: GPT-5.5, medium, native.

## Outcome

The core answer is correct: the run directly joins the pre-patch `HitTestMode.Block`, SDK hit-test semantics, the one-line `Block -> Default` patch, and its readback. It also correctly separates the failed R1 build from a later native R2 build/install and refuses to bind that later artifact to the patch.

The complete annotation is **not acceptable verbatim**. Its R2 behavior account begins cautiously as a saved walk-record claim, but then upgrades that record to “device evidence proves the click can advance.” The investigator did not independently replay the click or inspect the referenced screenshot/dump/run log, and neither the build nor the saved behavior record is bound to the C4 source state. The supported statement is narrower: a later stored walk artifact records one consent-to-Guide transition.

## Evidence grading

- **Static near cause — correct, high confidence.** The run opens R1 action `#4562` (raw call/output at physical lines 8026–8027), which exposes the outer Stack, four event callbacks, button/link handlers, and the visible-state `HitTestMode.Block`. It opens SDK outputs `#4598/#4601` (8047–8048, 8051–8052), which state that Block excludes children while Default permits self and children. It then opens the actual patch `#4607` (8066–8067) and readback `#4620` (8109–8110). This is strong code-level evidence, though not an A/B device proof of sole runtime causality.
- **R1 immediate verification — correct.** `#4620` reads back Default and shows an HAP timestamp preceding the patch; the R1 final report at line 8115 says the CLI build was blocked by missing `.migbot/config.json` and no new HAP was produced. The V5 report limits this claim to the 08-17 session.
- **R2 build/install — correct, high confidence.** The investigator opens native action `#5059` (R2 physical lines 840–841) and `#5062` (851–852). The output contains `BUILD SUCCESSFUL`, successful bundle installation, and `HAP installed`. This proves a later project build/install existed, not that the artifact contained this exact patch.
- **Saved behavior record — partly overstated.** The cited `#5191@L1073` is a native `jq`/report command reading saved `chunk0_handoff.json` and walk-ledger output. That artifact says the first-launch dialog was handled and “同意并继续” led into Guide. The investigator did open this output, but did not open or independently inspect the underlying screenshot, dump, or click log and did not perform a replay. “后续行走记录显示” is supported; “后续设备证据证明可点击推进” and the summary’s “实际验证最远到…点击…可推进” are too categorical.
- **Remaining interactions — correctly bounded.** Native `#6509@L4426` says LaunchAgreementDialog is page-level fail for text findings; consent progression is `skipped` by judge scope, reject is not taken through its dangerous confirmation, and links are displayed but not clicked. `#6511@L4430` is a child-agent report, not independent proof, but the native manifest output already supports the narrow boundary. The V5 answer does not claim four-click or full-page closure.
- **Patch binding — correctly unknown.** Neither R2 build output nor the stored walk artifact includes the target-source hash, HAP hash, or a read of the exact C4 line. Time ordering and a common project path do not establish inclusion or causal improvement.

## YAML, route, and `check`

The final YAML has six resolvable nodes and 18 locatable evidence references; its single explicit write edge is mechanically supported. V5 fixes V4's nonexistent `agent:__main__:01a009fe@v253`: the post-effect readback/build boundary is now attached to file v2. `entry: []` and v1 `无法确认` are defensible because no introducer for the Block line is established. R1 fixer `agent@v252`, R2 builder `agent@v17`, and the later evidence-reader nodes are not blamed for the original defect.

The actual route opened every source used for the four main conclusions: R1 source/SDK/patch/readback, R1 final limitation, R2 `#5059/#5062`, saved walk output `#5191`, and native judge output `#6509`. It did not merely rely on search snippets.

`check` was called twice:

1. The first draft returned `needs_review`, catching a drifted `#4564@L8032` citation and invalid `agent@v253`.
2. The second returned `mechanical_clear`, with zero issues. Its draft SHA-256 is `ef2069b7…ee01`; its canonical document SHA-256 `d8ec37d9…d1c4` equals the final-document hash recorded by the harness. The checked draft and final fenced YAML are character-identical after removing the draft's one trailing newline.

The original 5b770be run metrics/audit nevertheless labels both check calls `unverifiable` and `matched_check: null`: `probe._tool_output` reformatted the explicit text JSON instead of preserving its bytes for strict comparison. A later read-only audit using viewer `d14853c`—not the investigator source and not a changed model answer—replays the same recorded call IDs and exact original bodies, verifies both checks, and reports `matched_check: 58`. It does not alter the frozen old metrics. This agrees with the manual binding above; the distinction matters because the post-run viewer fix receives credit only for audit transport fidelity. Conversely, `mechanical_clear` does not authenticate semantic claims; neither viewer catches the saved-artifact behavior overstatement.

No red node is present, so the new red-node `basis` requirement is not exercised by this case. The lack of `basis` blocks here is therefore neither a pass for that feature nor a schema defect.

## V4 to V5 cost and quality

| Metric | V4 | V5 | Change |
|---|---:|---:|---:|
| Tool calls | 54 | 58 | +7.4% |
| Tool-return characters | 200,888 | 316,233 | +57.4% |
| Search calls / chars | 20 / 79,167 | 15 / 139,574 | — |
| Action calls / chars | 25 / 61,466 | 32 / 113,938 | — |
| Check calls / chars | 0 / 0 | 2 / 2,253 | — |
| Input total | 1,088,730 | 1,428,312 | +31.2% |
| Cache read | 973,824 | 1,264,640 | — |
| Uncached input | 114,906 | 163,672 | +42.4% |
| Output | 10,502 | 15,253 | +45.2% |
| End-to-end wall | 283.207 s | 335.656 s | +18.5% |
| Dollar cost | NULL | NULL | unknown |

The two check returns contain 2,253 characters, while the two submitted drafts total 8,197 characters and are generated and then re-enter context. Search/action returns also rise substantially relative to V4. These aggregates do not identify how much of the token/output/time increase was caused by `check`, draft repetition, wider investigation, or their interaction, so no single-factor cost attribution is supported. Input total already includes cached input, so cache-read tokens are not added again.

Compared with V4, V5 materially improves coordinate validity and preserves the direct later build/install boundary. It slightly improves behavior phrasing by naming a walk record, but the notes and summary still promote that record to proven device behavior. Thus: **core static diagnosis accepted; full annotation accepted only after downgrading the R2 behavior statement to a stored-record claim and retaining the no-binding caveat.**
