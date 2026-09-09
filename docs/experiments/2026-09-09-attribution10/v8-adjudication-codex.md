# V8 Codex C1–C4 adjudication

Scope: one GPT-5.5/medium/native tool-assisted run for each frozen C1–C4 question at source `b540cb2`. Judging is against the frozen `reference-v1/codex-reference.json` and raw R1/R2 only. Mechanical YAML/check/coverage status is reported separately and does not establish semantic truth. This four-case developer pass is not a holdout or a general efficacy claim.

## Results

| case | core | full annotation | fact-array grades | substantive boundary |
|---|---|---|---|---|
| C1 static no-op gate | accepted | accepted with recoverable omissions | partial, supported, supported | Direct earlier rule text is omitted, but closer BLOCKED, exact no-op patch, static PASS/no-build and false “mandatory parent callback” claim are correctly bounded. |
| C2 Works facade | accepted | accepted with recoverable omissions | omitted, supported, supported, omitted | Historical single-publisher summary and contaminated Works canonical are omitted. Fixer/reviewer conflict is correctly treated as claims; source equivalence and Works behavior remain unknown. |
| C3 GuideInit hypotheses | accepted | accepted with recoverable omissions | omitted, supported, supported, supported | Initial R1 Kotlin/layout/snapshot input and generation report are omitted. Both later hypotheses, reviewer counter-claim and final fresh-capture/manual-review debt are correctly tiered. |
| C4 dialog hit test | accepted | accepted with recoverable omission | partial, supported, supported, supported, supported | It does not enumerate all four Event declarations, but correctly establishes Block→Default, R1 validation limit, later native build/install, saved one-click manifest evidence and remaining patch/device boundaries. |

### C1

The report's static-gate/no-op conclusion is correct. It opens the closer BLOCKED message (R1 L3029), pre-patch source and actual patch (L3033/L3037), and closer PASS with `build_run:false` (L3065). It correctly rejects the main-session statement that the callback became mandatory because the default remains. It does not open the earlier direct rule at R1 L224, and it does not fully list unknown parent-call coverage or the platform form of a required `@Event`; these are recoverable completeness gaps.

### C2

The report does not invent a target file version when none is recoverable. It distinguishes the fixer summary at R2 L7682/7683 from the reviewer claim at L7680/L7686 and does not accept either as product-source truth. It correctly retains unknown code difference, error/timing/transaction behavior, exact HAP inclusion and Works device behavior. The reference fact that the earlier execution summary named one post-insert publisher (R2 L4934), and the system-contact contamination finding (L7574), are omitted. `coverage_complete=false` follows the absent target-file chain and is a delivery/accounting observation, not a semantic failure.

### C3

The report opens the Round 0 Monitor hypothesis record (R2 L6089), Round 1 reviewer counter-claim (L6957/L6963), Round 2 independent-mount summary (L7682/L7686), and final manual-review/fresh-capture debt. It explicitly says these are summaries/messages rather than reproducible source or device truth. It therefore supports the reference's competing-hypothesis conclusion. The missing initial R1 GuideInit input/generation claim is a recoverable fact omission; no false final-root-cause or visual-PASS claim follows.

### C4

The actual route opens the R1 source/SDK/patch/readback and final validation boundary, including R1 L8115. It then opens native R2 rebuild/install at L840 and the native command at L3917 that reads a saved capture manifest. The latter records one “同意并继续” `page_change` to `GuideStatusFragment`; it is not this investigator replaying the device or inspecting the referenced screenshot/dump/run log. The report preserves that distinction, does not bind the exact patch into the HAP, and does not extend one click to reject or the two agreement links. R2 build output occurs at 02:35 and the manifest-read record at 10:12; describing this as a later rollout build/install plus scenario record is supported, while patch causality remains unknown as stated.

## Delivery and cost

All four final references match their last checked drafts; semantic checking remains false. C1, C3 and C4 report mechanically complete coverage. C2 reports incomplete coverage because the target file has no recoverable chain/version; this does not erase its bounded conclusion.

| case | input total | cache read | uncached | output | calls | tool-return chars | wall | end-to-end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 | 395,626 | 344,064 | 51,562 | 7,210 | 31 | 84,582 | 169.530 s | 172.436 s |
| C2 | 934,641 | 811,520 | 123,121 | 9,713 | 48 | 475,213 | 230.477 s | 233.189 s |
| C3 | 2,188,513 | 2,027,520 | 160,993 | 18,305 | 90 | 243,762 | 400.306 s | 403.379 s |
| C4 | 1,107,183 | 1,013,248 | 93,935 | 11,071 | 39 | 150,061 | 257.648 s | 260.412 s |

Overall: core accepted 4/4. Each full annotation has at least one recoverable reference-fact omission, but none contains a major false causal attribution or behavior-closure claim. The large C3 cost and route variation preclude attributing cost to a single interface change from this n=1-per-case pass.
