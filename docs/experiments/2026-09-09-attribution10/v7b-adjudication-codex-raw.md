# V7 raw C1–C3 adjudication

Scope: six GPT-5.5/medium/native raw runs, two repetitions each for C1–C3. They received the same frozen question/pool but used shell over raw JSONL, not MigLoop's structured output contract. Prose format is not itself a semantic defect. Judging uses the frozen `reference-v1/codex-reference.json` facts, inferences, counterevidence and raw R1/R2 records. This is a developer-set baseline, not a holdout or general efficacy result.

## C1 — static no-op gate

Both repetitions pass the core question. They identify a generation-internal closer gate rather than a compiler or runtime repair, recover the exact `() => {}` → `(): void => { return }` patch, explain that both defaults remain no-ops, reject the main-session claim that the patch made the callback mandatory, and separate closer PASS from build/device verification.

| fact | rep1 | rep2 | note |
|---|---|---|---|
| rule forbids unregistered empty callbacks | supported | supported | Rep2 opens the direct rule at R1 L224; rep1 uses the operational closer BLOCKED record at L3029. |
| closer blocked on line 3 | supported | supported | Both cite R1 L3029. |
| exact patch, subsequent static PASS, no build in those closer records | supported | supported | Both use L3034/L3037/L3038 and L3065. |

Inference: supported 2/2. Unknowns are mostly supported. Neither fully enumerates whether every parent supplies a real callback or the platform-supported way to make `@Event` mandatory; these are recoverable omissions, not a wrong core conclusion. Both avoid claiming that closer `build_run: false` proves the whole later pool never built. Rep1 labels the native `patch_apply_end` UUID at L3038 as a “tool/event call”; the reference records no outer `call_id`, so this is a minor locator-label issue, not fabricated patch evidence.

Verdict: core accepted 2/2; full annotation accepted with recoverable omissions 2/2.

## C2 — Works facade dispute

Both repetitions pass the bounded core: fixer and reviewer claims conflict, product source/diff and Works-specific behavioral replay are unavailable, and neither same-DAO/event assertions nor build/install establish facade equivalence or repair of the missing-work symptom. They preserve unresolved transaction, timing, error-handling, DB, event-delivery and list-loading layers.

| fact | rep1 | rep2 | note |
|---|---|---|---|
| historical summary says one post-insert CREATED publisher | supported | supported | Rep2 cites R2 L4934; rep1 states the same bounded historical claim. |
| fixer says generation now goes through WorksService | supported | supported | Both cite the persisted fixer summary at R2 L7683. |
| reviewer claims same DAO/event, but complete relevant source is absent | supported | supported | Both tier this as reviewer evidence and keep semantic equivalence unknown. |
| Round 2 Works canonical was contaminated by system contacts | omitted | omitted | Neither discusses the R2 L7574 finding-index boundary. |

Inference and important must-reject boundaries: supported 2/2. Rep2's opening repeats that the reviewer called the edit equivalent, but the rest explicitly treats this as a counter-claim rather than source-proven truth. Both correctly state that later build/install is only build evidence.

Verdict: core accepted 2/2; full annotation accepted with the recoverable canonical-contamination omission 2/2.

## C3 — GuideInit competing hypotheses

Both repetitions pass the core: Monitor/visibility and independent mounting remain competing recorded hypotheses; the latter is more concrete but not proven as the true cause; final manual-review/fresh-capture debt prevents claiming behavioral closure.

| fact | rep1 | rep2 | note |
|---|---|---|---|
| initial GuideInit Kotlin/layout/snapshot input and generated progress-flow claim | supported | omitted | Rep1 reconstructs initial Android timing/step semantics and early implementation; rep2 starts at visual verification. |
| Round 0/1 remained low-confidence/transient-capture debt | partial | partial | Both establish persistent P2/manual-review debt without cleanly reproducing the full chronology. |
| Round 1 reviewer questions Monitor; Round 2 fixer records `currentStep===5` independent mount | partial | partial | Both recover independent mounting but only incompletely recover the specific earlier Monitor challenge. |
| final manual review/fresh capture debt remains | supported | supported | Both cite final/open state and do not convert build/install into visual PASS. |

Inference, unknown root cause and must-reject boundaries: supported 2/2. The missing initial-generation material in rep2 is a material fact omission for full annotation, but it does not reverse the bounded conclusion.

Verdict: core accepted 2/2; rep1 full annotation accepted with recoverable omissions; rep2 requires a material fact-completeness correction, with no major false cause claim.

## Per-run cost

| case/run | input total | cache read | uncached | output | calls | shell-return chars | wall | end-to-end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 rep1 | 716,836 | 597,504 | 119,332 | 7,740 | 15 | 3,506,378 | 172.467 s | 174.879 s |
| C1 rep2 | 773,947 | 594,432 | 179,515 | 6,374 | 13 | 2,961,631 | 160.072 s | 162.576 s |
| C2 rep1 | 1,572,761 | 1,436,160 | 136,601 | 12,053 | 22 | 2,515,979 | 289.955 s | 292.452 s |
| C2 rep2 | 1,197,405 | 970,240 | 227,165 | 9,690 | 18 | 1,784,115 | 234.119 s | 236.448 s |
| C3 rep1 | 1,037,870 | 883,200 | 154,670 | 8,553 | 13 | 3,813,998 | 197.126 s | 199.626 s |
| C3 rep2 | 1,905,106 | 1,717,760 | 187,346 | 9,576 | 18 | 4,420,185 | 237.344 s | 239.783 s |

Six-run mean: input total 1,200,654; cache read 1,033,216; uncached input 167,438; output 8,998; 16.5 calls; 3,167,048 shell-return characters; wall 215.181 s; end-to-end 217.628 s. Characters are not tokens, and large shell returns vary substantially by query route.

Overall: core accepted 6/6. Full annotation: five accepted with recoverable omissions; C3 rep2 needs material fact-completeness correction. No run makes a major false causal or behavioral-closure claim.
