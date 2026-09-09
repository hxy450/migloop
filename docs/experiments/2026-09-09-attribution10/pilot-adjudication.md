# GPT-5.5 native generic pilot adjudication

This is a bounded adjudication of three **generic full-file** pilot reports, not a formal same-question comparison against D1/D2/S1–S4. A missing reference fact is counted as an omission, not silently upgraded to a false claim. The reference witness checker authenticated 55/55 locators (`legacy-reference.json` SHA-256 `2c015536094fff1e42bb3b6b5cc2dce743c0f2a0f6924254027f7f8a5faac927`); this authenticates locations, not semantic truth.

## Outcome

| Case | Report | Assessment | Main result |
|---|---|---|---|
| D1 | `dice-entry/runs/tools/rep1/result.json:5` | Partial | Correct stage separation and bounded zero-hit language; validation/build-vs-device boundary omitted. |
| D2 | same | Partial | Correct later ECAT requirement and v8–v10 edits; post-repair successful build, WARN, and absence of an actively triggered callback test omitted. |
| S1 | `splash/runs/tools/rep1/result.json:5` | Partial | Initial BACK interception, Slice 11 assumption, finding, and onWillDismiss repair are right; entry-setup's deletion/D-020 transition and later build are omitted. |
| S2 | same | Partial | Correctly avoids saying windowFullscreen first appeared during repair; fails to identify the main session's concrete pre-write theme read. |
| S3 | `member-center/runs/tools/rep1/result.json:5` | Materially incomplete | The mask script is incorrectly left as practically unreconstructable; exact branches, three scanned builders, successful 3-site output, and the H5 skip are available in raw evidence. |
| S4 | same | Substantially complete | Correct source-input → intermediate → final price implementation chain, repair-introduced private error, narrow build fix, success, and device caveat. |

## Case findings

### D1 — test bridge

High-confidence supported fact: the report correctly separates the known original MainActivity/F001/immersive generation inputs from the later UI-test design and Step3 dispatch that added the Want→AppStorage bridge. It also limits zero-hit claims to known content. Witnesses include `agent-a70e555065a1dddd1.jsonl:36` (`call_f8b1ccd728e44d5fab88531c`) and `agent-a711c5d09fb676814.jsonl:37,39` (`call_6c1a…`, `call_04086…`).

Medium-confidence omission: it labels the builder touch as non-repair but never cleanly states what validation succeeded or that compilation would not prove the bridge ran on a device. No material false D1 claim was found.

### D2 — global exception observer

High-confidence supported fact: the ECAT feedback/dispatch is treated as a later gate, and import/call/observer edits are correctly assigned to v8–v10 without retroactively blaming the converter.

High-confidence omission: the full report never uses the later builder evidence at `dice-entry/pool/2f01bcdc-…/subagents/agent-a635575c78cd15ff6.jsonl:48,52` (`BUILD_EXIT_CODE=0`, plus WARN). It also omits that no test actively triggered an uncaught exception and observed the callback. This is omission, not a contradictory claim that no build occurred.

### S1 — privacy BACK chain

High-confidence supported fact: the initial converter received the disabled-BACK requirement and wrote `.onBackPressed(() => true)` (`agent-aconv-splash-…jsonl:71`, `toolu_01Np…`); Slice 11 later wrote the `isModal:true` explanation (`agent-aslice11-…jsonl:236`), and the fixer added `onWillDismiss` (`agent-a68daf…jsonl:346`).

High-confidence omission: the report lists entry-setup in `entry[]` but never explains its causal action. `agent-aentry-setup-…jsonl:123–124` (`toolu_013N…`) shows the before interception, the Navigation rewrite, the D-020 compromise comment, and the successful update. It also omits the later `agent-af0e…jsonl:37` successful build and the lack of repaired-device closure. No direct false S1 assertion was found.

### S2 — fullscreen system bars

High-confidence supported fact: the report explicitly says `windowFullscreen=true` existed in the pre-generation pool and narrows its zero-hit statement to conv-splash's observed range. Thus it does **not** make the prohibited claim that the requirement first appeared in the fixing stage. Its later hide/restore edit chain is supported.

High-confidence omission: the stronger witness is not named—main-session `9b3105a2-…jsonl:404` already contains `windowFullscreen` before the Splash write. The report also incompletely inventories the page-type/full-screen/safe-area generation inputs. Its statement that transmission into conv-splash is unconfirmed remains compatible with the reference and is not marked false.

### S3 — MemberCenter mask script

High-confidence omission: the report does not name the scanned `AppLoadDialog`, `PayAgreementDialog`, and `RenewRuleDialog` (`agent-a68daf…jsonl:81`); does not distinguish `Color.Transparent` for AppLoad from `Palette.DIALOG_MASK` for the other missing-mask controllers; and omits the already-transparent H5 controller that the script's skip rule leaves alone.

High-confidence unsupported/overstrong claim: the report says only output/self-report is known and exact target changes cannot be reconstructed because the ledger did not establish a target-file version. But `agent-a68daf…jsonl:103` (`toolu_01T6WkXMhD7rUsHaSaMPuhgx`) contains the actual transformation branches, skip rule, and write operation, while paired line 104 reports `3 sites` for `MemberCenterPage.ets`. Those records support the site/value reconstruction. They still do **not** prove device behaviour, so only that stronger behavioural conclusion remains unknown.

### S4 — price spans and private helper

High-confidence supported fact: the report follows the Kotlin numeric `replaceSpan` input (`agent-aslice8-pay-…jsonl:24`), the all-30vp implementation, the intermediate `ForEach(splitPriceRuns)` (`agent-a68daf…jsonl:528`), and the final `priceDigits/priceSuffix` two-Span implementation (`:592`). It correctly assigns the private-access compilation error to the visual repair and cites the narrow visibility correction and subsequent success (`agent-af0e…jsonl:24,32,34,37`). Its notes preserve the build-versus-device/all-format boundary. No material S4 omission or unsupported claim was found.

## Mechanical audit boundary

The separate member-center mechanical audit (`_migloop-eval-20260909/attribution10/audits/pilot-member-center.json`) reports unchanged pool/source/task, matched trace identity, 8/8 nodes resolved, and 28 evidence references accepted. It also records all 10 trajectory visits as unverified and no painted trajectory root. That latter result is an old-18ca512 parser/transport limitation for the GPT-5.5 native output shape, not a semantic model fault or a new-fix effect. Structural `verdict_ok`/`coverage_complete` therefore does not override the S3 raw-evidence finding above.

Overall, the pilot handled phase boundaries cautiously. The recurring weakness is omitted verification evidence; the one material factual adjudication problem is S3's overstrong treatment of a dynamically executed script as unreconstructable.
