# V6b C4 raw adjudication

Scope: the two prose/raw runs under formal-v6-document/codex-c4, compared descriptively with the four tool runs already adjudicated in v6-adjudication-codex. All use GPT-5.5/medium/native and the same frozen C4 task and two raw rollouts. Raw was not required to emit the YAML graph schema, so absence of node coordinates or a checked submission is not a semantic defect.

## Common raw truth

R1 rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl supplies the user symptom (physical L7997), pre-patch source and handlers (L8026-L8027), SDK Default/Block semantics (L8047-L8052), the actual one-line patch (L8066-L8067), readback (L8109-L8110), and the immediate no-new-HAP boundary (L8115).

R2 rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl supplies native later build/install output (L840-L841 and L7862-L7866), a saved walk record (L1073-L1074), a native read of the Harmony replay checkpoint/manifest (L3758-L3759), merged-manifest behavior summaries including consent page_change and unclicked reject/link branches (L4134-L4154), and later visual/judge failure boundaries (L4426-L4430). These records do not bind the exact patch to the built HAP or independently prove an A/B device effect.

## Raw rep1

Core: **accepted**. It reconstructs the full static chain and correctly says the R1 artifact predates the patch. It finds later native build/install/start evidence and does not equate it with behavior causality.

Full account: **accepted with a small evidence-level clarification**. It correctly locates the native output that reads the merged Harmony manifest, including LaunchAgreementDialog consent page_change, reject rendered-not-clicked, and agreement link unobserved. Calling this a “behavior observation” is faithful to the manifest field, but the strongest wording should remain “the saved visual-verify manifest records”; the investigator did not independently replay the click or inspect the referenced screenshot/dump. It correctly refuses full-interaction closure.

Citation/route: physical-line locators are usable, and the report distinguishes native outputs from a child-agent claim at L3977. It uses 15 command calls; broad JSONL searches return very large strings but do reach the decisive records.

## Raw rep2

Core: **accepted**. It correctly identifies Block-to-Default as a strong code-level near cause, records the exact patch/readback, and preserves the R1 no-build and patch-to-HAP/behavior unknowns.

Full account: **materially incomplete but recoverable**. It finds the Android-named walk handoff and a later signed Harmony build/install, then concludes that the later rollout reached only Android first-launch behavior plus Harmony build/install. The same R2 pool also contains the Harmony replay checkpoint/manifest and merged-manifest page_change records at L3758-L3759 and L4134-L4154. Omitting them understates later record-layer behavior evidence. The final conclusion that the patch itself was not behaviorally proven remains correct because those saved records are not source/HAP-bound or an independent replay.

Citation/route: R1 citations are precise. The run performs 19 broad command searches and sees many R2 matches, but does not resolve the later Harmony manifest evidence into the final answer.

## Raw versus four tool runs

- Core attribution is retained in all six reports: raw 2/2 and tools 4/4.
- Neither arm is uniformly better on complete semantics. Raw rep1 is strong and appropriately caveated; raw rep2 omits the Harmony record layer. Tool document rep1 omits the same direct layer, tool reference rep1 mildly upgrades a saved record to device-level wording, and both tool rep2 reports maintain the key boundaries.
- Tool reports add authenticated ledger identity, resolvable nodes/edges, coverage accounting, and checked-document delivery. Raw reports provide readable direct physical-line citations without that structure. Mechanical YAML/check success is not a truth advantage by itself.

## Cost observations

| arm | rep | input total | cache read | uncached input | output | calls | returned chars | result chars | wall | end-to-end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw | 1 | 1,333,553 | 1,178,624 | 154,929 | 8,060 | 15 | 3,714,096 | 4,198 | 190.415 s | 192.832 s |
| raw | 2 | 1,470,264 | 1,239,552 | 230,712 | 8,197 | 19 | 6,252,603 | 3,179 | 203.337 s | 205.965 s |
| tools, four-run mean | — | 1,357,133 | 1,218,304 | 138,829 | 13,104 | 58.25 | 252,465 | 2,097 | 283.725 s | 286.388 s |

Relative to the two-run raw mean, the four-run tools mean has 3.2% lower input total and 28.0% lower uncached input, but 61.2% higher output, 44.1% higher wall time, and 43.6% higher end-to-end time. Tool-return characters are 94.9% lower because raw shell searches repeatedly return large JSONL lines; characters are not tokens. Input total already includes cache read.

Thus this C4 slice does **not** demonstrate a 20–30% reduction in total input tokens. It does show a 28% uncached-input reduction, but the higher output/time and different investigation paths prevent treating that one metric as end-to-end cost superiority. With two raw and four tool developer observations, no statistical or general efficacy claim is warranted.
