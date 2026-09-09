# Formal-v4 C4 adjudication

Run: `_migloop-eval-20260909/attribution10/formal-v4/codex-c4/runs/tools/rep1`, frozen source `a579cdf`. This review does not project the later local `328f510` receipt-field fix onto the run.

## Outcome

The static code diagnosis remains **correct**. V4 materially improves the later build account by opening direct native R2 build/install output. Its full validation answer is not yet acceptable verbatim because it overstates a stored manifest observation as independently validated device behaviour and still emits the nonexistent R1 `agent@v253` node.

## Strong evidence and its limits

V4 directly opens R2 action `#5059` (raw tool result at physical line 840). That output shows:

- a HAP rebuild;
- `BUILD SUCCESSFUL in 1 s 581 ms`;
- successful bundle installation; and
- `HAP installed`.

This is a valid direct alternative to reference line 7694 for proving that a later build/install existed. The report correctly does **not** infer that #5059 contains the exact C4 patch: there is no later target-file version, source/artifact hash, or read edge tying that artifact to `Block -> Default`.

The source classification helped, but did not choose truth. The broad `hvigor` result's first R2 tool-output example is environment inspection `#4834@L399`, not a successful build. A later, focused HAP-path query exposes native output `#5059`, which the model then opens. This is the intended division: buckets identify record provenance; query refinement and raw action inspection establish what the record says.

## Manifest behaviour overclaim

Action `#6328` directly reads a stored capture manifest. The decoded artifact records:

- trigger `同意并继续`;
- outcome `page_change`;
- landing `GuideStatusFragment`; and
- paths to a screenshot, dump, and run log.

That is stronger than an unlocated agent summary, but the investigation did not open the referenced run log, screenshot, or dump and did not itself replay the device click. The safe conclusion is “a later manifest records one consent-to-Guide page-change observation.” The report's statements “这验证到了…行为层” and “实际行为验证最高到…page_change” are a medium-high-confidence overstatement.

This record also cannot establish C4 causality: no source/artifact identity binds the manifest to the one-line patch. No additional claim about later target-file changes is needed to establish that limitation.

The report correctly preserves the rest of the interaction boundary. Judge output `#6509` leaves consent progression skipped, marks the page fail for title/content, and does not pass reject or link navigation. It therefore does not claim a full page or four-click closure.

## YAML and coordinates

- `entry: []` is defensible: the Block line is visible, but its introducer and device causality are not established.
- R1 main@v252 is correctly `正常`; its two duplicate nodes are redundant but consistent.
- R2 main@v17 is correctly `正常` for the narrow build/install action, with patch binding explicitly unknown.
- R2 main@v118 is too positive as `正常` if its reason continues to call the manifest independent behaviour validation; use an artifact-record boundary or `无法确认`.
- `agent:__main__:01a009fe@v253` is still invalid. The ledger has versions 1..252. The a579cdf searches clamp v253 requests to `≤v252` and issue no v253 receipt target. Tail actions are valid boundary evidence, but do not create an agent version.

The mechanical audit resolves 7/8 nodes and locates all 16 evidence references. This shows the evidence strings exist; it does not rescue the invalid v253 node or validate manifest semantics.

## Receipt metadata boundary

The frozen a579cdf receipt still writes action kind into `field`: a displayed tool-output hit such as #5059 appears as `field:"other"`. The displayed action and via target are genuine, so this does not invalidate navigation or the opened native output. The later 328f510 metadata correction did not affect this run and receives no retroactive credit.

## Search and cost comparison

| Metric | V3 | V4 | Change |
|---|---:|---:|---:|
| Tool calls | 51 | 54 | +5.9% |
| Tool-return characters | 261,628 | 200,888 | -23.2% |
| Action calls / chars | 27 / 84,784 | 25 / 61,466 | — |
| Search calls / chars | 16 / 119,995 | 20 / 79,167 | — |
| Full-pool searches / chars | 4 / 4,634 | 7 / 12,623 | — |
| Agent searches / chars | 12 / 115,361 | 11 / 65,030 | — |
| File searches / chars | 0 | 2 / 1,514 | — |
| Input total | 1,262,524 | 1,088,730 | -13.8% |
| Cache read | 1,120,256 | 973,824 | — |
| Uncached input | 142,268 | 114,906 | -19.2% |
| Output | 10,548 | 10,502 | -0.4% |
| End-to-end wall | 263.682 s | 283.207 s | +7.4% |
| Dollar cost | NULL | NULL | unknown |

V4 uses more calls but substantially less tool text and input. It is slower wall-clock, so the cost result is mixed rather than uniformly better. `input_total` already includes cached input; cache-read tokens are not added again.

V4 makes no pipe-as-OR mistake and no integer `until` call. Different search literals are not compared to infer a cutoff bug.

## Paired conclusion

Compared with V3:

- static diagnosis: unchanged and correct;
- direct R2 build/install evidence: improved;
- patch/artifact binding: still correctly unknown;
- behaviour evidence wording: regressed from cautious claim-level language to overstatement of a stored manifest;
- invalid v253 node: not fixed;
- input/tool-text cost: lower, wall time: higher.

The core code answer is accepted. The complete annotation requires two substantive corrections: remove v253, and downgrade the manifest from independently validated device behaviour to a recorded later observation with no C4 causal binding.
