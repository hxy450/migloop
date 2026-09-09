# V3 bounded preflight: C4 later-verification discovery

Scope: frozen Formal-v2 C4 run, its two allowed rollout roots, current frozen `source-733c526` query implementation, and frozen reference-v1 witnesses. No model was run and no raw command was executed. Character counts below are decoded tool-return text characters; they are not tokens or transport-envelope bytes.

## Finding

The R2 build was missed because the investigation never performed a full-pool, post-patch time-window search. It used the R2 root as `sid`, but every one of its seven search calls constrained `agent=__main__:01a009fe`, the R1 main agent. `sid` selected the shared two-root ledger; it did not make an agent-scoped search include the R2 main agent `__main__:01a021e5`.

This is visible in the run itself:

- `result.json` records 34 calls and 167,145 returned text characters.
- The seven searches returned 43,185 characters. All seven were scoped to the R1 agent; full-pool searches: **0**.
- The first validation query used `hvigor|build|compile|HAP|...` as though `|` were alternation. The tool performs literal substring matching, so it returned zero. A second pipe-delimited query had the same problem.
- Later searches used `after=true`, but still inside R1 agent v252/v253. `after` exposes post-anchor hits in that same agent scope; it does not cross into a later root/agent.
- The returned scope line explicitly said other agents were excluded. The model's last progress message even noted that the search was “主会话记录，不是全池否定,” but its final boundary generalized this to “没有新 HAP、安装.” Thus the final error is also a conclusion self-consistency failure, not merely hidden evidence.
- Sixteen `action` calls (68,377 characters) plus two `agent` calls (42,499 characters) consumed 110,876 characters, 66.3% of all tool text, mostly deepening the R1 code/SDK/build-failure account. The code diagnosis benefited, but no forward validation window was opened.

The GUIDE did contain the relevant principle: evidence after an agent version is not input to that earlier write, but later repair/counterevidence/validation should be investigated in a separate later agent/time window. The run followed the first half (do not contaminate prior input) but did not operationalize the second half.

## Actual minimal neutral path

I replayed only current read-only query/render functions against the same frozen pool. The path does not assume whether a later validation exists; it starts from the target's recorded change time, scans the allowed pool after that time, and then opens a returned candidate.

### Minimal existence discovery: 2 calls, 3,102 characters

1. `file(target, v=2, readers=true, ...)` — the same call already made by Formal-v2 C4.
   - Return: 2,057 characters (`events.jsonl` use line 16, result line 17).
   - Neutral fact exposed: v2 was written by R1 main v252 at `2026-08-17T03:11`; this supplies the lower time bound.
2. Full-pool time-bounded search after that timestamp for a generic build-success marker, with no `agent` or `file` restriction.
   - Current source-733c526 return: 1,045 characters including the search receipt.
   - It reports one later agent, R2 main `01a021e5`, nine matches, and first candidate action `#5059@L840`.

This two-call path is enough to reject the unqualified proposition “the allowed pool contains no later successful build.” It costs 1.9% of the V2 run's 167,145 tool-return characters.

### Confirm build and installation in native output: 3 calls, 4,592 characters

Add:

3. `action(__main__:01a021e5, #5059, part=output, find=<build marker>, max_chars=2000)`.
   - Return: 1,490 characters.
   - The same native output contains a successful build, successful bundle installation, and `HAP installed`.

Incremental cost after the already-open target file is only two calls and 2,535 characters. The three-call total is 2.7% of the original tool text. This proves later build/install existence, but still does **not** bind that artifact to the exact C4 patch or prove the four click behaviours.

### Recover the exact frozen-reference R2 anchor: 4 calls, 8,810 characters

For exact audit alignment rather than mere existence, an additional R2-agent time-window search returns all nine build-success hits, including action `#7859@L7693` (whose tool result is physical line 7694). Opening `action #7859` with a 2,500-character output window returns 1,231 characters and shows `BUILD SUCCESSFUL in 12 s 22 ms`, successful HAP installation, and `HAP installed`.

The measured sequence is:

| Step | Return chars | What it establishes |
|---|---:|---|
| Target `file@v2` | 2,057 | Change actor and timestamp |
| Full-pool post-change search | 1,045 | A later R2 build candidate exists |
| R2-agent bounded search | 4,477 | All R2 matches, including `#7859@L7693` |
| `action #7859` output | 1,231 | Native build/install output at the reference anchor |
| **Total** | **8,810** | Exact later-window witness, still without patch/artifact identity |

## Failure classification

1. **Scope-selection error:** selecting the R2 root as `sid` was mistaken for searching R2 activity; all searches still named the R1 agent.
2. **Query-semantics error:** pipe-separated terms were sent to a literal-substring search.
3. **Direction error:** the investigation thoroughly walked backward/locally from the target writer but did not perform a separate forward-in-time validation pass.
4. **Evidence-to-conclusion error:** the model explicitly recognized its search was not full-pool, then wrote a pool-wide negative conclusion.
5. **Not a retrieval-capacity problem:** a 1,045-character full-pool return exposed the missed later agent, well within the remaining call and text budget.

## Neutral V3 guard recommendation

Do not put an expected build result or reference anchor into the task prompt. Instead, make the shared overview/guide require this content-neutral protocol for every claimed repair:

1. Record the repair timestamp or last changed version.
2. Enumerate validation windows after that point across every allowed root, using a full-pool time scope before narrowing to an actor.
3. Keep three conclusions separate: validation activity exists; an artifact was produced/installed; that artifact and behavioural replay are bound to this exact repair.
4. If the report says no later validation exists, require a full-pool search receipt or an explicit `coverage_out_of_scope` statement. An actor-scoped zero hit cannot support the negative.
5. State that multi-term search is literal unless the tool explicitly documents alternation; otherwise issue separate small searches.

This changes procedure rather than leaking C4's answer.

## S3 dynamic-mask truth boundary recheck

The frozen MemberCenter mask reference remains supportable at a command-execution boundary, with a narrower caveat than “final source/device truth”:

- `agent-a68daf720e780b4c2.jsonl:81` lists the three missing-mask controllers in `MemberCenterPage.ets`: AppLoadDialog, PayAgreementDialog, and RenewRuleDialog.
- Physical line 103 (`toolu_01T6WkXMhD7rUsHaSaMPuhgx`) contains the actual script/command input. It skips a controller block already containing `maskColor`; assigns `Color.Transparent` for AppLoadDialog and `Palette.DIALOG_MASK` for other missing-mask controllers; calls `open(path,'w').write(new)`; and invokes the script.
- Its paired physical line 104 is a non-error, non-interrupted tool result with empty stderr. Native stdout reports `3 sites ... MemberCenterPage.ets` and total 51 sites.
- The earlier Slice 8 source witness at line 264 contains the H5 controller's existing `Color.Transparent`; the script's skip rule explains why it was not one of the three edits.

Therefore it is fair to say the recorded script execution applied those branches to the three scanned missing-mask sites at that moment. It is **not** fair to infer from this alone that all three edits survived later writes, that the final file was read back byte-for-byte, or that any dialog passed device verification. The reference should be read at this bounded “executed dynamic write + paired native result” level.
