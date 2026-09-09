# V5 preflight design review

Verdict: the proposed `check(sid, draft)` is useful as a **structural preflight**, provided its result is never presented as semantic validation and the checked draft is cryptographically bound to the final YAML. It directly targets recurring failures such as C4's nonexistent `agent@v253`, malformed candidates, missing refs, inconsistent `entry`, and coverage drift. It cannot decide whether a manifest proves device behaviour, whether a reviewer is right, or whether a build contains a patch.

Implementation resolution before freeze: this is the initial design review, not a description of final code. The implemented binding uses the **last submitted check**, never falls back to an earlier successful check, and preserves warnings when that last document matches. Hashes bind content but are not server signatures or tamper-proof authentication. All five basis fields are required when basis is supplied; explicit unknown counterevidence is allowed, and old reports without basis still load. See [the final adversarial review](v5-check-review.md) for actual implementation and tests.

## Required guardrails

1. Return language must say `structure/locator only`, not `correct`, `verified`, or `evidence supports claim`. A resolved reference proves location only.
2. Bind the latest successful check to the final YAML. Return a SHA-256 of the exact normalized/parsed draft, and have the harness/audit compare it with the emitted verdict. Otherwise a model can check one draft and output another; every edit after diagnostics must be rechecked.
3. Do not let `check` open nodes, satisfy route coverage, create navigation receipts, or expose suggested replacement nodes. It is a validator, not an alternate search/oracle.
4. Parse with the same loader/canonicalization as the final verdict. Reject or bound duplicate YAML keys, aliases, custom tags, depth, node count, scalar size, and total draft bytes; otherwise checker/final-parser disagreement or resource abuse is possible.
5. `node.basis` should remain optional for old/non-red nodes. For `进入·错/进入·缺`, require nonempty `expected`, `actual`, `expected_evidence`, and `actual_evidence`; treat `counterevidence` as optional or allow an explicit bounded-unknown statement. Requiring all five unconditionally encourages fabricated filler. Evidence fields should be typed reference lists whose locators resolve, without claiming their text entails the prose.
6. `entry` validation should require every entry node to exist in the same defect and carry a red entering role; a fixer/normal/unknown node must not pass as entry. `repair.after` may appear as a normal/unknown explanatory node, but never as a red origin merely because it was modified.
7. Edge checks should validate endpoints and declared ledger relation separately. An explicit `候选` edge may be structurally legal but must not be reported as causal truth.
8. Keep legacy verdict loading independent of V5 basis requirements. “Old block loads” should not silently mean “old block passes V5 check.”

## What counts as improvement

A `check` call or green structural result is not the outcome metric. On the paired Member/C4 runs, improvement means:

- fewer invalid coordinates, missing/mismatched references, malformed candidates, entry/role contradictions, and coverage errors;
- red nodes contain inspectable requirement-versus-actual basis without increasing fabricated semantic certainty;
- no regression in critical facts: dynamic script versus final/device truth for Member, and immediate build versus later build/install versus patch/device binding for C4;
- final semantic adjudication improves or holds, independently of YAML validity;
- the final verdict exactly matches the last passing checked draft.

Report every run, not only successful checks. One Member and one C4 run can demonstrate concrete paired changes, not statistical significance.

## Cost accounting

The new tool changes both behaviour and cost. Record separately:

- number of `check` calls, failures, retries, return characters, and elapsed time;
- total draft characters sent on every check, including failed attempts;
- GUIDE growth and `basis` output growth;
- total input, cache read, uncached input, output, tool-return characters, calls, wall, and end-to-end wall;
- whether the final response is bound to the last passing draft.

Do not subtract check overhead from headline run cost or compare only the final successful attempt. A lower semantic error rate with higher tokens/time is a quality-cost tradeoff, not a free improvement. Dollar cost remains unknown when NULL.

## `run_pair.py` integration points

Current file: `docs/experiments/2026-09-09-fidelity-cost/run_pair.py`.

- Add `check` to `MCP_TOOLS` at lines 30–31. This updates Claude `--allowedTools` at line 312 and makes provider-origin guarding recognize the new leaf.
- Native Claude/Codex event and transcript parsers are generic enough to count a returned `check` automatically in `tool_calls` and `tool_chars`; pending/error/rejected states are also already counted. No special whitelist is needed for basic recording.
- Add explicit derived metrics: `check_calls`, `check_chars`, `check_failures`, `check_retries`, checked-draft SHA(s), last passing SHA, and `final_matches_checked`. Generic totals alone cannot distinguish validator overhead or detect draft swapping.
- Add `check` to `src/migloop/probe.py::_MIGLOOP_TOOLS`. `_step_node` should treat it as a non-navigation validation step, not map it to a file/agent visit. Audit output should preserve its call/result and hash binding without painting investigation coverage.
- `via.trace_identity` need not let check replace the required `sessions`/search identity evidence. If check returns ledger identity, record it as a consistency observation only.
- Keep connectivity smoke guide-only; otherwise historical smoke comparisons acquire an unrelated extra call.

Recommended acceptance gate for V5 experiments: the run remains valid if check fails and the model reports that failure; it is not silently repaired or retried by the harness. A structurally passing, hash-bound final YAML proceeds to independent semantic adjudication exactly as before.
