# V7 C4 adjudication

Scope: two tool-assisted runs at formal-v7/codex-c4, source 84bfcf8, GPT-5.5/medium/native, judged against the frozen reference-v1 C4 fact array and raw R1/R2 records. Mechanical schema/check/submission success is separate from semantic correctness.

## Raw boundary

- R1 rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl: source output shows the four Event callbacks and visible-state HitTestMode.Block (physical L8026-L8027); SDK output defines Default self+children response and Block child blocking (L8047-L8052); the actual patch and readback show Block→Default (L8066-L8067, L8109-L8110); R1 build was blocked and its HAP predated the patch (L8115).
- R2 rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl: a later same-project build/install succeeds (L840-L841; the reference alternatively anchors L7694). It carries no target-source/HAP binding. A native command later reads a saved Harmony manifest recording center [636,1536], consent page_change and GuideStatusFragment (L3917-L3918). This is saved record evidence, not the investigator replaying the click or proving the patch caused it.

## Rep1

Fact-array grading:

1. **Partial:** the report supports the visible Block line, but does not state the fact that the source exposes all four Event callbacks.
2. **Supported:** it opens and accurately uses the SDK Default/Block semantics.
3. **Supported:** it opens the patch and readback and states Block→Default.
4. **Supported:** it accurately limits R1 to source readback and a pre-fix HAP after config-blocked validation.
5. **Partial with a material overclaim:** it opens native R2 build/install. However, it calls later time plus the same project path “补丁进入后续构建/安装产物”的较强过程证据. Those facts prove a later project build, not patch inclusion. The notes later say exact inclusion remains unknown, making the report internally inconsistent.

The core inference is supported: Block is a strong static near-cause candidate, but the four dialog interactions were not device-regression-closed. The report also preserves unknown alternative layers at a high level.

Material omission: its actual route does not open the R2 Harmony walk/manifest records at L1073-L1074 or L3917-L3918. It instead stops at a main-session statement, plan and visual reports, then says no independently reviewable click coordinate/state assertion was seen. That is an investigation omission: the pool contains a saved Harmony manifest with those fields. The omitted artifact still would not prove patch causality or four-click closure.

Delivery: two checks. The first reports a duplicate-role warning; the corrected second draft is mechanically clear and is the exact draft referenced by the accepted final submission. semantic_checked=false, so this does not cure the binding overclaim.

## Rep2

Fact-array grading:

1. **Partial:** it supports the visible Block line and event-chain wiring but does not enumerate the four Event callbacks stated in the reference fact.
2. **Supported:** SDK semantics are opened and accurately described.
3. **Supported:** actual patch success and source readback support Block→Default.
4. **Supported:** it correctly separates R1’s config-blocked build and pre-fix HAP.
5. **Supported:** it opens native R2 build/install and says exact source/HAP binding is indirect and unknown, rather than treating time ordering as proof.

The core inference and unknowns are supported. Rep2 also opens action #3717@L3917, whose native output reads the saved Harmony capture_manifest and exposes coldstart, click center [636,1536], page_change and landed GuideStatusFragment. The report correctly calls this manifest/tool-output evidence, explicitly says it did not inspect the referenced screenshot/dump, and keeps “不同意” and both links unverified. It does not claim an independent replay or patch-caused behavior.

Delivery: two checks. The first reports a duplicate-role warning; the second is mechanically clear and is bound by the accepted final reference. semantic_checked=false.

## Comparison and cost

Rep2 is semantically stronger than rep1 because it finds and correctly tiers the Harmony manifest and avoids the patch-to-HAP overclaim. Both retain the static core. Neither enumerates the four callbacks, a recoverable fact omission rather than a wrong cause.

| run | input total | cache read | uncached input | output | calls | tool-return chars | result chars | wall | end-to-end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V7 rep1 | 1,553,896 | 1,439,744 | 114,152 | 15,590 | 75 | 172,087 | 269 | 349.785 s | 352.616 s |
| V7 rep2 | 1,624,706 | 1,511,424 | 113,282 | 16,278 | 82 | 236,654 | 433 | 360.082 s | 362.794 s |
| V6 reference mean | 1,285,937 | 1,165,312 | 120,625 | 12,255 | 60 | 209,021 | 269 | 267.375 s | 270.031 s |

Against the two-run V6 reference mean, V7’s two-run mean has 23.6% higher input total, 5.7% lower uncached input, 30.0% higher output, 30.8% more calls, 2.2% fewer tool-return characters, and about 32.8% higher wall time. A shorter default guide did not produce an aggregate cost reduction in this two-run developer slice. Different investigation routes and stochastic run variance prevent assigning the changes solely to guidance disclosure.

Overall: core accepted 2/2; full annotation rep1 requires material correction, rep2 accepted with the stated four-Event omission. This is developer-set evidence, not a general efficacy result.
