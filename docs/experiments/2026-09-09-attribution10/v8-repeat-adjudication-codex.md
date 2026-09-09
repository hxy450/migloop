# V8 repeat Codex adjudication

Scope: second GPT-5.5/medium/native tool-assisted repetitions for frozen C1–C4 at source `b540cb2`, judged against `reference-v1/codex-reference.json` and raw R1/R2. Mechanical schema/check/coverage status is separate from semantic correctness. No private holdout material is used.

## C1 — static no-op gate

Core: accepted. Full annotation: accepted with recoverable omissions. Fact-array grades: partial, supported, partial.

The report correctly identifies the generation-internal illegal-placeholder gate, exact no-op-to-explicit-return patch, unchanged default runtime semantics, and lack of proof that the callback became mandatory or was click-tested. It preserves unknown old-line authorship and does not turn later builds into targeted behavior validation. However, the direct rule text available at R1 L224 is omitted, and the direct second closer PASS with `build_run:false` at L3065 is replaced by a more cautious discussion of the later writeback at L3135. Those omissions reduce fact completeness without changing the core result.

No major extra error. Its statement that later successful builds give limited evidence that this syntax did not break compilation is indirect because exact patch-to-artifact binding is absent; the report does not claim targeted coverage.

## C2 — Works facade dispute

Core: accepted. Full annotation: accepted with recoverable omissions. Fact-array grades: omitted, supported, supported, omitted.

The report correctly keeps the fixer and reviewer accounts as conflicting source claims, refuses to invent a target `file@v`, and leaves actual facade equivalence, code diff, DB/event timing and Works list/device behavior unknown. It omits both the historical single-publisher summary at R2 L4934 and the system-contact contamination of the Round 2 Works canonical at L7574. These are relevant context but do not reverse the bounded conclusion.

No major extra error. `coverage_complete=false` is caused by the missing target-file chain/version and remains separate from semantic grading.

## C3 — GuideInit competing hypotheses

Semantic content of the checked draft: core accepted; full annotation accepted with recoverable omissions. Fact-array grades: partial, partial, supported, supported.

The draft correctly keeps Monitor/visibility and independent mounting as competing recorded hypotheses, opens the Round 1 reviewer counter-claim and Round 2 fixer/reviewer messages, and retains missing source diff, fresh capture and device closure. It improves the initial-input account with the Android view structure, GuidePage coverage/`initStep` slot and early converter message, but still does not fully recover the reference's initial Kotlin/layout/snapshot plus generated 5110 ms progress-flow claim. The persistent low-confidence/transient-capture chronology is also only partial. These are recoverable completeness omissions; no false root-cause or behavior-PASS claim appears.

Formal delivery: rejected. The actual final response contains only a `migloop-verdict-ref/1` block. The single recorded check at step 71 returned text but was not authenticated to the current ledger trajectory; `submission.json` reports `status: rejected`, binding `unverifiable`, `matched_check: null`, and there is no `verdict.yaml` or `findings.json`. The captured check draft above can be reviewed as model semantic content, but cannot be substituted for an accepted final document. Thus this run passes semantic-candidate core grading but fails the formal delivery requirement.

## C4 — dialog hit test

Core: accepted. Full annotation: accepted with recoverable omission. Fact-array grades: partial, supported, supported, supported, supported.

The report recovers the Block→Default source/SDK/patch chain, R1's source-only validation and pre-fix HAP, the later native build/install, and later saved navigation evidence while keeping exact HAP inclusion unknown. The action at R2 L1073 is a native command reading an edgewalk handoff, and L3122 is a native command reading phase-2 manifests: they support that the rollout saved a “同意并继续” path into Guide, not that this investigator independently replayed the click or inspected underlying screenshots/dumps. The report mostly states that tier explicitly. Its phrase that the rollout “实际验证到了” the behavior layer is slightly strong in isolation, but the surrounding manifest/tool-output limitation prevents a material closure overclaim.

It does not enumerate all four Event declarations, a recoverable fact omission. It correctly keeps reject and both agreement links untested, does not bind the source patch into the HAP, and treats the later LaunchAgreementDialog visual `fail/elements_missing` as a distinct UI-alignment result rather than disproof of the consent click.

No major extra error.

## Delivery and cost

| case | input total | cache read | uncached | output | calls | tool-return chars | wall | end-to-end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 rep2 | 591,227 | 519,680 | 71,547 | 8,985 | 42 | 122,951 | 195.500 s | 198.362 s |
| C2 rep2 | 1,170,957 | 1,005,056 | 165,901 | 8,166 | 38 | 893,876 | 198.106 s | 200.925 s |
| C3 rep2 | 1,986,766 | 1,868,288 | 118,478 | 14,098 | 71 | 180,391 | 345.437 s | 348.322 s |
| C4 rep2 | 1,171,408 | 1,058,816 | 112,592 | 12,869 | 52 | 208,998 | 321.790 s | 324.919 s |

C1/C2/C4 final references match the last checked drafts. C1/C4 coverage is mechanically complete; C2 coverage is incomplete for the absent target chain. C3's reference does not match an authenticated check and is rejected. These facts do not certify semantic truth.

Four-run mean: input total 1,230,090; cache read 1,112,960; uncached input 117,130; output 11,030; 50.75 calls; 351,554 tool-return characters; wall 265.208 s; end-to-end 268.132 s. Characters are not tokens.

Overall: semantic-candidate core accepted 4/4; accepted formal delivery 3/4. C1, C2 and C4 full annotations are accepted with recoverable omissions. C3's captured draft would also be accepted with recoverable omissions, but its actual final submission fails closed and is not replaced by that draft.
