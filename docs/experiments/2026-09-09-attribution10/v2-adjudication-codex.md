# Formal-v2 Codex paired adjudication

This compares V2 C2/C4 with their Formal-v1 reports using the same pointed questions and frozen pools. The only intended change is the generic GUIDE family; the reports were not given reference answers. Newer formatting or a newer GUIDE is not itself credited as semantic improvement.

## Result

| Case | Core answer | Full annotation | Paired change |
|---|---|---|---|
| C2 Works facade | Accept | Accept after minor bounded corrections | Material improvement: competing claims now remain unknown instead of treating the reviewer as truth. |
| C4 hit test | Accept | Requires material correction | No improvement on the key error: the later build/install window is still omitted. |

No V2 report is accepted verbatim as a full annotation.

## C2 — WorksService facade

V2 report: `_migloop-eval-20260909/attribution10/formal-v2/codex-c2/runs/tools/rep1/result.json:5`

Core: **correct (high confidence)**. V2 consistently treats the fixer summary, reviewer response, and subsequent summary patch as conflicting source claims. Because `PptGenerationViewModel.ets` source/diff and a Works-specific runtime check are absent, it concludes that neither changed behaviour, behavioural equivalence, nor repair of the missing-work symptom is established. It also acknowledges later build/install without mistaking that for Works behaviour verification.

This fixes V1's material semantic error. V1 adopted the reviewer assertion that the same DAO/event meant an equivalent facade replacement and no contact with the real cause. V2 explicitly refuses that inference and replaces V1's red fault roles with neutral `无法确认` roles.

Remaining bounded issues:

- Medium-confidence omission: the contaminated Round-2 Works canonical at R2 line 7574 is not cited. The report already reaches the proper unknown conclusion from missing source/runtime evidence, so this does not alter its core answer.
- Medium-confidence YAML weakness: the `候选` edge from main@v22 to main@v242 is not a demonstrated dispatch/causal edge. Raw records show an earlier requirement and later same-session completion claim, but not that exact lineage. The hedged relation limits the damage.
- A repair object containing only competing-summary evidence can misleadingly suggest a confirmed product repair; it should say “claimed repair” or remain absent.

Coverage improvement is real but bounded: V1 invented a path-shaped candidate; V2 uses `coverage: []`. The harness may still report `invalid_manifest` because the target itself is absent from the ledger. That underlying condition is not renewed model fabrication.

Must-reject check: **pass**. V2 neither claims the facade fixed Works nor treats same DAO/event or build success as behavioural proof.

## C4 — LaunchAgreementDialog hit test

V2 report: `_migloop-eval-20260909/attribution10/formal-v2/codex-c4/runs/tools/rep1/result.json:5`

Core: **correct (high confidence)**. V2 again provides the strong static chain: clickable descendants, outer visible Stack using `HitTestMode.Block`, SDK definitions, exact `Block -> Default` patch, and post-patch readback. It does not claim four device interactions passed.

Material residual error: **high confidence**. The report again says there was no new HAP/install and that verification stopped at R1 build-entry failure. That is valid only for the immediate R1 window. R2 line 7694 (`call_dacW1PmSvf6UGEA9wFwJcdnz`) later reports BUILD SUCCESSFUL and HAP installed. The later artifact lacks a source/artifact hash and four-click replay, so it cannot be bound to C4; nevertheless, its existence cannot be omitted or denied.

The correct verification statement is:

1. Immediate R1 validation was blocked; the HAP inspected then predated the patch.
2. A later R2 build/install succeeded.
3. No evidence uniquely binds that artifact to the exact C4 source state or verifies the four click paths.

YAML is otherwise mostly consistent. One role became less precise: V2 marks main@v252 `无法确认`, although the actor's SDK investigation, exact edit, and readback are known. Behaviour is unknown; the code-fixer role is not.

Must-reject check: **fail** on the pool-wide later-build boundary. The direct-source and no-device-regression boundaries pass.

## Paired conclusion

- Core acceptance: C2 and C4.
- Unconditional full-annotation acceptance: neither.
- C2 becomes acceptable after minor annotation corrections.
- C4 still requires a material correction to its verification timeline.

The GUIDE-only V2 change therefore shows a material improvement on C2 but no improvement on C4's central residual error. With only two paired cases, this supports a promising but non-uniform effect—not a blanket quality claim.
