# Formal-v1 Codex adjudication

Status: **complete**. These runs received explicit pointed questions, unlike the earlier generic pilot. Core causal correctness, recoverable omissions, YAML role/entry semantics, and mechanical transport validation are evaluated separately.

## C1 — static empty-callback gate

Report: `_migloop-eval-20260909/attribution10/formal-v1/codex-c1/runs/tools/rep1/result.json:5`

Core answer: **correct (high confidence)**. It correctly identifies this as an in-generation static placeholder-gate correction, not a compiler or post-execute repair. It also correctly says `() => {}` → `(): void => { return }` leaves the default callback with no business side effect, preserves the unknown of a parent-supplied callback, and does not treat closer PASS as a click/runtime test.

Recoverable evidence error: **high confidence**. The report repeatedly says the v1 target line was unrecoverable and known only from the closer message. Frozen raw line 3034 (`call_cITFznZwW17SBIwTS2wQhbj0`) directly returns the pre-patch source line `@Event onAnswer ... = () => {}`. This is a false evidence-characterization claim, but it does not reverse the core no-op/static-gate conclusion.

YAML semantics:

- `entry` points to main@v108 even though that node is marked `正常` and is the correcting writer. If `entry` denotes defect origin, the known faulty state is file v1; its original writer remains unknown. This is a medium-high-confidence fault-location inconsistency.
- File v1 is marked `无法确认`, but the empty default callback itself is directly observable at line 3034. Only the writer/full context is unknown.
- The mechanical audit marks both v1/v2 coverage rows out of scope because this generation-internal correction has no repair-manifest versions. That structural mismatch is separate from semantic correctness.

Must-reject check: passed. The answer does not call this a compiler fix, does not say the event became mandatory, and does not say closer PASS proves event progression.

Mechanical boundary: `_migloop-eval-20260909/attribution10/audits/formal-v1-codex-c1.json` records unchanged inputs, matched identities, 3/3 nodes resolved, and 10 evidence refs accepted, but invalid coverage and native visits left unverified/unpainted. The latter diagnoses the b197227 native transport-envelope/parser path, not the answer's semantics.

## C2 — WorksService facade dispute

Report: `_migloop-eval-20260909/attribution10/formal-v1/codex-c2/runs/tools/rep1/result.json:5`

Core answer: **partially correct with a material boundary failure (high confidence)**. It correctly says the target source/diff is unavailable and does not claim the facade change fixed Works. However, it then accepts the reviewer's claim that the old and new paths are behaviourally equivalent and that the change did not touch the real breakpoint. The raw pool contains conflicting fixer/reviewer summaries, not complete class source or a valid Works retest. Same DAO plus a same-named event does not establish equal transaction, error, timing, or side-effect behaviour.

Important omission: **high confidence**. Raw line 7574 (`call_rHkspr6Fzhub0xEU83VOrdsF`) says the Round-2 Works canonical captured system contacts. The report omits this contamination and overstates the finding summary as a valid observation of generated works missing. That leaves both “fixed” and “definitely untouched” unproved.

YAML semantics:

- Marking `visual-fixer-summary.md@v2` as `进入·错` and main@v227 as `带病传递` encodes the unverified reviewer opinion as truth. These should remain conflicting/unconfirmed claims.
- The coverage candidate is a target path rather than a manifest candidate hash, so coverage is mechanically invalid.
- Empty `entry` is defensible while origin is unknown, but the later red roles negate that restraint.

Must-reject check: failed. The answer avoids “WorksService fixed it,” but effectively adopts the equally unsupported opposite: same DAO/event proves behavioural equivalence and the real cause was untouched.

## C3 — GuideInit competing hypotheses

Report: `_migloop-eval-20260909/attribution10/formal-v1/codex-c3/runs/tools/rep1/result.json:5`

Core answer: **correct (high confidence)**. The report treats the Monitor/visibility attempt, the Round-1 reviewer objection, and the `currentStep===5` independent-mount attempt as competing, incompletely verified hypotheses. It explicitly refuses to infer true cause or repaired visual outcome from reviewer opinion, self-report, paths, or gate results, and asks for source diff plus fresh capture/compile/retest.

Recoverable omissions:

- Medium-high confidence: it misses the early baseline at R1 line 2013 (`call_b5NIkmLWkXtjLgHjdKGnc9WQ`) and line 2781: GuideInit Kotlin/layout/snapshot input already existed during generation, and the generator reported its 5110ms progress flow implemented. This omission matters for chronology, but the report does not falsely say the requirement was new in verification.
- Medium confidence: it does not consolidate the Round-0/1 `low_confidence`/transient-capture status and the final two manual-review debts, though it does independently preserve the not_found and fresh-capture caveats.
- Medium-high confidence: it omits the later R2 line 7694 BUILD SUCCESSFUL/install evidence. This later build cannot be bound to the GuideInit patch and is not visual verification, but it must be distinguished from the fixer's own narrower “未编译、未复测” step.

Scope ambiguity: the v225 node correctly scopes “未编译、未复测” to the fixer reply at line 7653. The final notes repeat the phrase without that scope; taken as a pool-wide claim it is overbroad because line 7694 records a later build/install. The supported conclusion remains that no fresh capture closes GuideInit visually.

YAML semantics:

- High-confidence error: `repair.before` and `repair.after` both name the same external-input `GuidePage.ets@v1`. No file version/diff establishes v1 as both sides of a repair. This contradicts the report's own correct statement that the source repair is unrecoverable; the repair object should be absent/unknown.
- Empty `entry`, `无法确认` roles, and unresolved coverage are otherwise appropriately conservative and do not encode either reviewer or fixer as ground truth.

Must-reject check: passed. It does not invent a late requirement, use reviewer opinion as proof, or equate SBS/build-like evidence with visual closure.

## C4 — dialog hit-test boundary

Report: `_migloop-eval-20260909/attribution10/formal-v1/codex-c4/runs/tools/rep1/result.json:5`

Core answer: **correct (high confidence)**. Pre-patch source, the four event bindings, SDK definitions, exact patch, and source readback make `HitTestMode.Block` a strong code-level near-cause candidate. The report correctly does not claim that the four click paths passed on-device.

High-confidence omission: R2 line 7694 (`call_dacW1PmSvf6UGEA9wFwJcdnz`) later reports BUILD SUCCESSFUL and HAP installed. This cannot be uniquely bound to the C4 patch because there is no source/artifact hash or C4 click replay, but it must be included in a two-root rollout-wide verification account.

Medium-high-confidence scope error: the R1-specific claims are sound—validation was blocked by missing `.migbot/config.json`, and the then-inspected HAP predated the patch. The unqualified boundary/notes/final statements that no new HAP was produced or installed become false or misleading across the full pool. The accurate formulation is: immediate R1 build blocked; later R2 build/install exists; C4 patch-to-artifact identity and four click behaviours remain unverified.

YAML semantics are otherwise mostly sound: v1→v2, fixing agent, SDK node, readback, and write edge match direct evidence. Empty `entry` is defensible because the original writer is unknown. `带病传递` for v1 is slightly stronger than the accompanying “direct candidate” caveat, but the SDK evidence makes the candidate strong.

Must-reject check: failed only on the pool-wide “no later successful build” boundary; source/patch, immediate pre-fix HAP, and no-device-click boundaries pass.

## Final acceptance split

- Core pointed-question acceptance: **C1, C3, C4 (3/4)**.
- Core rejection: **C2**, because it turns the reviewer's same-DAO/same-event opinion into a resolved equivalence/root-cause conclusion.
- Unconditional full-annotation acceptance: **0/4**.
- Full annotation acceptable after bounded corrections: **C1, C3, C4**.
- Full annotation rejection: **C2**.

This is not a “10/10 all pass” result. The distinction matters: C1/C3/C4 found the central causal boundary, but each still contains an evidence-window or YAML-annotation error that would pollute a training/evaluation label if accepted verbatim.
