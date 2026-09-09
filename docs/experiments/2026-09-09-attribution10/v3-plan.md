# Formal-v3: time scope and claim diagnostics

Written before v3 model runs. This remains development regression, not a fresh holdout or a migration-benefit test.

## Frozen comparison

Use Formal-v2 `member-center` (S3/S4) and `codex-c4` unchanged common tasks and raw pools. Run one new tools replicate per group with GPT-5.5 / medium / native MCP, 1800-second timeout, no automatic schema repair, no selection of best run. Freeze this revision's source separately; preserve all earlier outputs and reference-v1. No actual migration, deployment, or device validation is run.

## Hypotheses

- Supplying an explicit whole-pool time horizon and an anchored future-window query recipe makes later-root evidence discoverable without exposing any expected answer. C4 must distinguish local earlier lack of build, existence of later build/install, and unproven patch/artifact/behaviour identity.
- `out_of_scope` prevents “not requested in this question” from becoming “not a repair.” All manifest entries stay in the denominator. Warning on literal changes marked `not_repair` does not prove they fix bugs or alter the old claim.
- Separate executed-script evidence from file-state reconstruction. Missing formal versions cannot alone refute recorded execution, and recorded execution cannot prove later persistence or device success.
- UI displays model claims and machine advisories separately; added time metadata never creates model visits or historical causal edges.

## Interventions

Shared per-session use/done time overview (`index(kind=time)`, compact file/agent/sessions headers, HTTP time-scope metadata); exact ISO-time comparisons in pool file search; explicit literal-substring query semantics; four coverage statuses; structural self-consistency advisories for entry roles and repair anchors. New regression tests cover unknown times, mixed offsets/precision, invalid cutoffs, unchanged claims, and HTTP/MCP consistency. No task-specific names, reference answers, or witness coordinates are added to GUIDE.

## Decision rule

Keep semantic grading from protocol-v1, with explicit errors rather than a blended score. Peer reviewers inspect original evidence. A YAML-valid report or an accounted manifest is not a pass. Report raw calls, wall and end-to-end time, input_total, cache_read, uncached input and output. The target is fewer specified errors with audit invariants intact, not a guaranteed n=1 cost win. General performance or stability requires repeated and unseen cases.

Ledger identity note: correcting `atoms.search_pool` changes the conservative whole-module builder fingerprint. Old runs are not rebound to the new ledger; use their frozen viewers for historical display. The difference is provenance, not proof that underlying historical versions moved.
