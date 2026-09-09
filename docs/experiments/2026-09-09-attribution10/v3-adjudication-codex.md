# Formal-v3 C4 adjudication

Run: `_migloop-eval-20260909/attribution10/formal-v3/codex-c4/runs/tools/rep1` (`source_code_id=18b8f7f`). This review uses the unchanged frozen reference-v1 and both allowed rollout roots. A valid YAML parse is treated only as structural evidence.

Correction note: an earlier draft incorrectly compared two different search literals and called that a late-read cutoff reproduction. That inference was wrong and has been removed below.

## Outcome

Core answer: **correct (high confidence)**. Full annotation: **acceptable after bounded corrections**.

V3 preserves the strong static chain: the pre-patch outer Stack used `HitTestMode.Block`, descendants had click handlers, the SDK says Block prevents child hit-test responses while Default permits them, the patch changed exactly that value, and a readback saw Default. It correctly calls this a strong code-level near-cause rather than four-click device proof.

Most importantly, V3 fixes V2's material timeline error. It scopes “no new HAP” to the immediate R1 attempt, then separately acknowledges later R2 new-package installation and privacy-gate/replay evidence. It does not bind those later observations to the exact C4 patch because no later target-file version/hash is recoverable and the R2 main record has no `HitTestMode` literal.

The must-reject boundary therefore passes: V3 does not deny source/patch evidence, does not claim four interactions passed due to this patch, keeps the immediate R1 HAP pre-fix, and no longer says the entire pool had no later build/install.

## Recoverable evidence omission

V3 finds later installation/replay activity, but cites main-session statements and a child-agent completion report. It does not open the stronger direct builder witness at R2 physical line 7694/action `#7859`, whose native output contains `BUILD SUCCESSFUL in 12 s 22 ms` and `HAP installed`.

This is a medium-high-confidence omission, not a reversal of the answer: even the direct builder output lacks a source/artifact hash and C4 four-click replay, so the correct patch-binding conclusion remains unknown.

## YAML role and time consistency

- `entry: []` is correct: changed blame cannot identify who introduced Block.
- R1 main v252 is correctly `正常` because its diagnosis, SDK read, patch, and readback are directly evidenced. This improves V2's overly uncertain fixer role.
- High-confidence coordinate error: `agent:__main__:01a009fe@v253` is outside the ledger's valid 1..252 range. Search rendered tail activity as `喂 v253 (锚点之后)`, but that tail/feed label is not a valid agent node. The post-patch actions may remain boundary evidence without inventing an agent@v253 node.
- High-confidence locator error: the same node cites `#...:4618@L8096`; action #4618 is physically at lines 8100–8101, while line 8096 is a different response item. The mechanical audit consequently resolves 3/4 nodes and reports 15 evidence refs OK plus one missing.
- Medium-confidence time ambiguity: R2 node v181 cites line 6505/action `#7439`, which belongs to v185. That is valid **later boundary evidence**, but it was not input to v181. Mark it as subsequent evidence or place it on a v185 boundary node.
- Repaired file v2 appearing as a `正常` node is not treated as an error. The operative rule forbids marking repair.after red/faulty; a normal node explaining readback/verification is allowed, though potentially redundant.

The verdict parser reports no schema errors and complete empty coverage. That does not validate these temporal or semantic annotations.

## Query audit

| Measure | V2 | V3 |
|---|---:|---:|
| Total tool calls | 34 | 51 |
| Tool-return characters | 167,145 | 261,628 |
| Full-pool searches | 0 | 4 |
| Full-pool search characters | 0 | 4,634 |
| Single-agent searches | 7 | 12 |
| Single-agent search characters | 43,185 | 115,361 |
| Pipe-as-OR mistakes | 2 | 0 |

V3 meaningfully improves scope discipline: it performs four searches from the patch timestamp through the reported pool end, opens `index(kind=time)`, sees both session groups, and searches R2 main through v231. It never uses `|` as pseudo-OR.

The remaining retrieval inefficiency is query choice. Full-pool `hvigor` returns the earliest R2 match, a system-prompt mention, not the builder. The later R2 `install` query returns 26,022 characters of mixed material. The model opens earlier installation statements but not direct action `#7859`. Thus it found the correct later window but not the strongest concise witness.

## Time-scope review and correction

The known line-7694 build was **not** excluded by the chosen upper bound: `2026-08-22T15:24:42.229Z` is later than that event, and the subsequent R2 agent@v231 searches have no time cutoff. Missing the exact anchor was a search/follow-through issue.

This run does **not** reproduce the recently fixed `agent(until=<action sequence>)` late-read bug. It makes zero integer-`until` calls. My earlier comparison was invalid: the full-pool zero-hit query searched literal `点击同意`, while the later 20-hit R2-agent query searched different literal `同意并继续`. Different terms cannot establish a cutoff discrepancy. The time index still states that some action timestamps may be missing/unsortable, but no specific C4 miss can be attributed to that here.

## Paired conclusion

Compared with V2:

- Static diagnosis: unchanged and correct.
- Later build/install existence: materially improved; V3 acknowledges it instead of denying it.
- Exact native builder evidence: still omitted.
- Patch-to-artifact and four-click binding: correctly unknown.
- Fixer role: improved from `无法确认` to `正常`.

V3 therefore fixes V2's core residual timeline error. Its remaining defects are the invalid v253 node, one bad locator, a bounded v181/v185 evidence-window ambiguity, and evidence selection; the core answer is accepted and the full label is accepted only after those corrections.
