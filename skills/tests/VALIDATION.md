# Skill bundle validation — 2026-09-17

The initial 2026-09-17 checks covered skill instructions and scripts only. Later dated checks below include the shared inquiry changes needed by self-contained card validation; they do not deploy the renderer/server or modify global hook configuration.

## Final-card contract, not a draft approval pipeline (0.8.0, 2026-09-25)

- One shared `card_contract.py` owns the authored template and final checked-graph admission rules. Required title/when/description/summary, nonempty recommendations and graphs, and a declared deviation are checked; prose meaning is not. New cards require successful, unchanged graph receipts. No repair actor, final-version authorship or repair-window write anchor is required.
- `pack` no longer has `--draft-only` or publishes failed cases/views. A relation failure returns structured graph feedback, `card: null`, and a nonzero CLI exit. The inquiry run still saves feedback for the next ordinary/force submission. The investigator keeps the original YAML, and only a successful final draft becomes a case. Ingest and new lesson source binding reuse that contract. Existing historical records remain readable and are not silently reclassified.
- Coordinate-card prose is no longer parsed for implicit e-ID validation; structured relation/force evidence remains byte-, actor- and time-checked by the canonical kernel. An opaque invocation need not literally contain its target path. Context-only trees no longer count as completed attribution delivery. UI response fields remain compatible.
- Lesson proposals default to active after normal model synthesis and format/source checks. Explicit unresolved/disputed states and source-withdrawal propagation remain available, but no independent reviewer or intermediate approval stage is added. Instructions clarify concrete conditional rules and move old-card environment maintenance out of the investigator's main flow.
- Full regression: **660 passed, 1 skipped in 64.49 seconds** across `skills/tests` and all `tests/test_inquiry*.py`. The existing Windows symlink skip remains. Fixtures now use real synthetic tool calls and checked cards instead of the removed unchecked-packing shortcut. These are contract tests, not a new model attribution score.
- After making lesson publication default to active, the focused card/memory suite passed **74 tests in 14.72 seconds**. All four installed packages are 0.8.0 and their instruction hashes match source. A separate installed `python -I -S -B` run produced a valid synthetic card and ingested it through the standalone maintain package; no sibling/source imports were needed. Previous installation backup: `C:/Users/hongy/.codex/.migloop-skill-backups/20260925T102016Z-8b4117e23d3d`.
- Browser smoke passes: **27 queries, zero JavaScript errors**; loading, freeze/unfreeze, original/diff expansion, and model-review dashed edges remain intact. Artifacts: `C:/Users/hongy/projects/_migloop-card-contract-20260925/browser-1/`. Test server/browser exited afterward.
- No historical application, original transcript, existing memory store, hook installation or remote server was changed. Old source cards that failed earlier rules need a real repack before new ingestion/rebinding; this change does not invent a successful receipt for them.

## Evidence-backed supplemental file nodes (0.7.5, 2026-09-23)

- Compact drafts can declare an unrecorded input/intermediate file using an explicit path. The first ordinary submission persists `unrecorded_file` feedback; only an eligible unchanged edge in the same investigation may later use the existing force reason and original call/return references. No node-level force/evidence fields were added. Unknown agents, unrecorded targets and ambiguous/bare unknown identities still fail.
- A successful incident force marks the file `existence_basis=model_review`, with `exists=false` retained. Every other handoff still needs its own evidence. Nodes live only in the checked report/card; `files`, `effects` and source identities remain unchanged. Reload, manual report-overlay traversal and compact card storage retain the distinction. The UI adds only a supplemental-node notice and reuses its existing dashed styling, not a new renderer.
- The existing force checker verifies source bytes, agent ownership, endpoint times and native contradictions. A request with a paired later return cannot backdate completion even when its shell effects were not parsed. File effects/causal semantics remain model judgments; a genuine tool call alone is not proof of an arbitrary claimed effect.
- **643 passed, 1 skipped in 84.11 seconds**, across `skills/tests` and all inquiry tests. The 24 new cases cover first-force rejection, changed endpoint/session isolation, foreign calls/messages/fake references, native contradictions, late opaque returns, unresolved branches, two forced handoffs around an intermediate file, source tampering, Codex call/output records, tree projection and end-to-end card packing. One existing lexical-path test now expects saved unresolved feedback instead of immediate rejection; ordinary basename substitution remains unbound. Other diagnostic tests retain catalog suggestions.
- Headless Chrome `tests/browser/inquiry_tree_smoke.cjs` passes, including supplemental node labeling/dashed styling, source access, report/manual tree behavior and freeze controls; zero JavaScript errors. Dedicated browser/server exit afterward. Artifacts: `C:/Users/hongy/projects/_migloop-supplemental-nodes-20260923/browser-1/`.
- Focused real replay: the unchanged 0723 GuideInit generator transcript alone leaves its shell-read mapping file unindexed. The exact skill example first produces missing-file feedback, then its existing L50-L51 force evidence yields a complete loadable graph without adding another agent's path-registration records. Global file/effect tables are unchanged. This is a controlled missing-index test, not full-pool coverage or a new model accuracy trial. Receipts: `C:/Users/hongy/projects/_migloop-supplemental-nodes-20260923/real-input/`.
- Installed bundle smoke under `python -I -S`: the packaged CLI accepts a previously checked synthetic force draft as `valid/complete/ready_for_review`. First installation hit a transient Windows directory lock and rolled back; retry succeeded with backup `C:/Users/hongy/.codex/.migloop-skill-backups/20260923T073625Z-b2bd2beb6211`. Source/installed skill text hashes match; the skill and JS syntax validators pass.
- This iteration changes the canonical inquiry checker, compact evidence projection, one UI notice, instructions and tests. It does not change collectors, global index schema, lesson merging/recall, historical card contents, application projects or remote server deployment. Earlier uncommitted environment/example work is preserved.

## Paired teaching examples and minimal graphs (0.7.4, 2026-09-23)

- Card instructions distinguish same-file historical writes from necessary cross-file handoffs. Unrelated later wiring may remain in the narrative; the graph need not enumerate it or the repairer. A spec writer still needs the actual spec/consumer bridge if it did not write the target. A historical write edge does not certify final whole-file authorship or semantic survival.
- Two real teaching branches: 0723 GuideInit image constraints (correct inputs, wrong implementation) and Jetsnack915 pixel-unit contracts (source-to-spec deviation, downstream implementation). Their paired lesson examples retain actionable APIs/formulas while leaving resource ratios, project variable names and measured screen widths in the cards. No new draft fields, mandatory checks, checker behavior, or merge protocol.
- Original input, write, continuation and repair citations were inspected. Both graphs were exercised on focused indexes of unmodified original transcripts, including prior path-registration context. Ordinary first submissions received feedback for unparsed shell reads; reviewed second submissions passed with **image: 2 native + 1 reviewed edge**, **units: 2 native + 2 reviewed edges**. The source coordinate uses the actually registered Git Bash path. This is example validation, not full-pool coverage, independent model performance, or a causal-accuracy score.
- Local receipts and first/final graphs: `C:/Users/hongy/projects/_migloop-skill-examples-20260923/real-4/`. Teaching cases are disclosed examples, not unseen evaluation samples. No newly spawned model trial was run.
- Four new contract tests validate the full example schemas and graph shapes: a direct original write survives later same-file wiring/repair without adding their agents; a cross-file shortcut without the actual consumer is rejected. Existing tests publish every lesson example/template through real ingest/apply/export with synthetic valid source bindings.
- **619 passed, 1 skipped in 85.90 seconds**, across all `skills/tests` and `tests/test_inquiry*.py`; both skills pass `quick_validate`. Installed 0.7.4 instructions are byte-identical to source and the standalone card CLI runs under `python -I -S`.
- Updated only skill instructions, package version, documentation and new contract tests for this iteration; the uncommitted 0.7.3 environment feature remains preserved. Existing memory content, source cards, inquiry core, UI and project hooks were not edited. Installation backup: `C:/Users/hongy/.codex/.migloop-skill-backups/20260923T064858Z-eb41e5e890b3`.

## Historical card environment (0.7.3, 2026-09-23)

- Metadata scanning pairs recorded CC/Codex calls with successful replies. It extracts literal SDK/catalog/toolchain configuration and a small set of plain environment probe replies; it does not execute historical commands, read today's checkout, resolve a BOM, or infer runtime SDK from target/compatible SDK.
- `pack` automatically includes compact `environment` observations before the card cutoff, with value, basis, timestamp, reference, source hash, generation/repair phase and explicit unknowns. Unsupported or untimed records remain unknown. Model drafts gain no required fields; DevEco's existing header-only metadata path is unchanged.
- `cases.py enrich` produces new versions of existing cards after checking material identity/hashes. Original cards, authored draft/claims, graph evidence and validation remain unchanged. Normal memory ingest invalidation and explicit apply re-binding remain in force; no new automatic approval or merge rule.
- **149 passed, 1 skipped in 36.11 seconds** across `skills/tests`, including 14 new cases for config versus narrative/docs, failed/unacknowledged calls, secrets exclusion, CC/Codex pairing, BOM versus resolved-library distinction, historical cutoffs, automatic pack integration, additive/idempotent enrichment, mismatched histories and retained review gates. Both changed skill instructions pass the skill validator.
- Follow-up shared-core regression: **615 passed, 1 skipped in 63.39 seconds** across `skills/tests` and all `tests/test_inquiry*.py`. The installed 0.7.3 card package also re-enriched a real card under `python -I -S` with the identical revision, confirming self-contained packaging and idempotence.
- Real Jetsnack915: the currently retained 90 JSONL files contain matching hashes for all source references used by the 15 existing cards. One shared metadata scan found eight distinct version facts before the observation cutoff: Android compile/target 36, min 23, Kotlin 2.3.21, AGP 9.1.0, Compose BOM 2026.05.00, HarmonyOS target/compatible 6.1.0(23). Each enriched card retains about 4 KB compact environment context. Unknown versions stay unknown; this does not claim SDK installation, deployment, or cross-version validity.
- No changes to inquiry core, UI, applications, lesson text, memory-merge logic or recall policy. This is metadata enrichment, not a new attribution or migration-benefit experiment.

## Optional checks and actionable lessons (0.7.2, 2026-09-22)

- Lesson proposals may omit `check` or supply `[]`; normalization retains the legacy field as an empty list. Nonempty actions and exact case/claim/revision evidence remain required. Invalid check types fail before publication.
- Reading exports show nonempty checks as optional, with task-triggered use and reuse of existing evidence/tests. Empty checks have no section. Existing stored lessons and historical snapshots are not rewritten by export.
- Maintenance examples retain public API/mechanism details, add small Builder/unit-order contrasts, separate unrelated mechanisms, and make the proposal template's check field optional. Recall adopts the same semantics, including old packages headed “检查”.
- **135 passed, 1 skipped in 28.02 seconds** across `skills/tests`. The Windows symlink skip is unchanged. Eleven new parameterized cases cover omitted/empty/malformed checks, retained action/evidence requirements, old-store export, and actual publication of the skill's YAML example/template with synthetic valid evidence. Both changed skills passed the skill-creator validator.
- The existing 12-lesson real memory was locally refined to 13 lessons by separating Material sizing and unilateral inset. Its 43 evidence bindings still cover the same 15 unchanged cards; the exported 33 Markdown files have valid hashes and 79 resolving links. This is an incremental editorial revision, not another independent model run or evidence of migration speed/accuracy improvement.
- No inquiry core, UI, server, application code or project hook changes.

## Self-contained skills and transferable lessons (0.7.1, 2026-09-21)

- Published skills carry their required pure-Python runtime and YAML parser. The build-cards package uses the canonical inquiry core; other packages do not include that core. Build outputs are generated outside the repository, not a second maintained implementation.
- Card packing prepares/reuses a source- and kernel-fingerprinted index. A checked declared path must reach its target but does not require a separate repair-writer anchor. Coordinate and path diagnostics identify affected fields, branches and next checks. Tests retain rejection of missing/invalid relations and reversed time.
- Optional card `unknown` and inherited per-graph summary/recommendations reduce repeated authoring without altering the original draft. Force remains review-gated and requires original tool-call evidence.
- The Claude Code first-write checkpoint and its standard-library installer are included. Installing skills does not install project hooks automatically.
- The maintenance skill now defaults to file-based navigation and includes a transferability test, positive/negative examples and a complete lesson-body example. Cases retain historical details; lessons express conditional mechanisms and actions, not project identifiers or historical measurements as new defaults.
- **590 passed, 1 skipped in 64.26 seconds** across all `skills/tests` and `tests/test_inquiry*.py`, with the existing environment's Python and `PYTHONPATH=src`. A dedicated external pytest directory avoided unrelated temporary-directory permissions.
- Independent GPT-5.6 Sol high, zero-context run: unchanged 15 source cards into an empty store produced 12 active lessons. All 43 source references resolved, covering 15 cards; the input and stored cards matched byte-for-byte. This verifies output structure/source integrity, not cross-project migration benefit or every technical claim.
- The earlier run that was given the previous 27 lessons was stopped and excluded from the from-cards experiment. It was a revision exercise, not a clean reconstruction.

Reproduce the regression subset from the checkout using Python with pytest and the source development dependencies:

```text
python -m pytest skills/tests tests/test_inquiry*.py -q -o pythonpath=src --basetemp NEW_EXTERNAL_TEST_DIRECTORY
```

Shells that do not expand globs (including PowerShell for native commands) should enumerate `tests/test_inquiry*.py` into an argument array first.

## File-readable memory publication (0.5.0, 2026-09-19)

- Added `memory.py export`: root and per-topic `index.md` files expose only direct children/direct lesson previews; individual `*.lesson.md` files preserve full text, applicability, exceptions, dependencies and exact case/claim/revision bindings. Only active lessons are published. No model call or re-distillation is performed.
- Default application bundles contain no cards or local store paths. `--link-cards` adds development-only relative links to exact stored card versions, without copying cards. A manifest records the source snapshot and content hashes. Existing output is refused; a new directory is published only after all files have been staged. The source store remains unchanged.
- The recall skill now uses ordinary file reading, parallel branch selection and task-based stopping. Source review includes the card's unknowns. The maintenance skill publishes the reading bundle after semantic maintenance; JSON store operations and legacy recall diagnostics remain compatible.
- **157 passed, 1 skipped in 28.08 seconds**, using the existing bundle/inquiry integration subset plus **18 new publication tests**. New checks cover one-level disclosure, mixed direct lessons/subtopics, exact source links, portable application packages, dependency links, identity preservation after recategorization, withdrawal exclusion in new releases, missing descriptions, existing-output/store-overlap rejection, partial-write failure, damaged evidence, complete long text and the CLI outside the repo. These are software contracts, not model recall or migration-improvement scores.
- Both updated skills passed the skill-creator validator. GitNexus reports the shared maintenance CLI as touching multiple existing flows; all those operations remain covered by the regression suite, and the change adds a dispatch branch rather than rewriting store methods.
- Real Jetsnack915 smoke export: source `7e883fd5…` retained, **24 active lessons / 23 topic directories / 49 files / 127 checked links**. All source-store file SHA256 values were unchanged. The 3 candidate lessons remain in the store, not in the reading bundle. Root index is 657 UTF-8 bytes; this is an entry-size measurement, **not** an end-to-end token saving.
- Existing releases are immutable historical copies. Withdrawal does not erase distributed copies: the maintainer must export and hand off a new entry point. Automatic host/hook/OBS publication remains unimplemented. No new Opus/Luna behavioral trial was run for this change.

## Stage/context routing (0.4.0)

- Cards and lessons preserve `when` as the task stage/action and `description` as the observable input context. New templates carry both; old records remain accepted without inferred text, ID changes or snapshot rewrites.
- Browse/search expose description in compact previews. Full-body lexical search also includes description, with title/when/description matches weighted above body matches. There is no hard stage gate.
- The first three skills now contain their complete procedures and templates in SKILL.md. Recall alone retains progressive reading of experience. The old card.md path redirects to the canonical template for existing callers.
- **139 passed, 1 skipped in 14.23 seconds** on the same bundle + 80-test integration subset. The skip remains Windows symlink creation. Four static skill validations passed. Coverage includes new-field roundtrip, real checker/view compatibility, old-card/old-lesson reads, invalid field types, context-only search, cross-stage retrieval, compact previews and dependency invalidation after a context update. These are contract tests, not a new model attribution or semantic-recall score.

## Instruction rewrite and recoverable installation (0.3.0)

- Four concise, action-first SKILL entrypoints; task formats and queries are loaded at the relevant step. Card graphs describe input → deviation → repaired file, without a required repair-agent node. Multi-file issues can deliver representative chains while explicitly retaining unresolved targets.
- Installer now supports `--update` with a durable backup and `--restore` to the same destination. All replacement packages are staged first; publication errors roll back; rollback failures retain recovery data. A lock prevents concurrent installations. Unrelated skills and global configuration are untouched. Force-kill/power-loss recovery is manual, not an atomic four-directory guarantee.
- **125 passed, 1 skipped in 11.35 seconds**: bundle/install tests plus the existing 80-test inquiry/DevEco/product subset. The skip is a symlink-creation test unavailable under the host's Windows permissions. Tests exercise copy failure, partial publication rollback, retained recovery data, restore/re-restore, source overlap, unrelated packages and explicit unresolved targets.
- The current card template was instantiated with two synthetic input → deviation → target examples and an unresolved third file; both graphs passed the real checker without a model-declared repairer. This covers native repair anchors, not opaque-script anchor completeness.
- Four skill-creator validations passed; relative documentation links resolve. Installed four packages exactly match repository content (excluding Python cache files).
- Actual developer update backup: `C:/Users/hongy/.codex/.migloop-skill-backups/20260918T035403Z-6c3062c55d66`. This was produced by the new installer, not a manual copy. Instruction simplification is not a new attribution-accuracy claim.

## Four-skill revision (0.2.0)

- Split migration-wide triage from single-issue investigation; their CLI entrypoints reject each other's commands.
- Four packages passed skill-creator's static validator. The development installation was manually backed up for that revision; the 0.2.0 installer itself supported first installation only. Automated update/backup/restore is introduced in 0.3.0 above.
- Cards retain when, summary, recommendations and compact graph views. Multiple deviation origins and shared input nodes are preserved. The existing inquiry checker remains the only read/write graph checker.
- Final retained state is the operational repair target; no additional task to prove repair effectiveness. Historical reversals and new requirements must still be distinguished.
- **111 targeted tests passed in 9.77 seconds** (31 bundle tests plus the same 80 existing tests below). These are contracts, not attribution-accuracy scores.
- One fresh GPT-5.6 Sol/high forward trial uses an existing 0723 triage issue, frozen source materials and only a skill/task-location prompt. See `docs/experiments/memory-skills-20260917/` for its reproducible launcher and separate semantic review.

## Original three-skill revision (0.1.0): automated checks

- 28 new bundle tests: mixed-model/source provenance, metadata separation, CC/Codex/DevEco reading, packaging/target coverage, immutable versions, evidence withdrawal, transitive invalidation, conflict/cycle rejection, paging/search, independent installation and CLI operation.
- 80 existing targeted tests: previous DevEco lookup/product harness/skill package checks, inquiry compact cards, declared trees and force submissions.
- Combined result: **108 passed in 10.76 seconds** on Python 3.12. Explicit UTF-8, `pythonpath=src`, and a new isolated pytest base directory were used.
- The official skill-creator validator passed for all three SKILL.md packages.
- The optional card packaging integration calls the existing inquiry checker and verifies its real mechanical result; it does not manufacture a second graph validator.

Reproduce (use a new writable temporary directory, not a shared directory containing data):

```text
python -B -X utf8 -m pytest skills/tests tests/test_deveco_bare_id.py tests/test_inquiry_product_pair.py tests/test_inquiry_skill_package.py tests/test_inquiry_case_card.py tests/test_inquiry_declared_tree.py tests/test_inquiry_force_submission.py -q -p no:cacheprovider -o pythonpath=src --basetemp NEW_TEST_DIRECTORY
```

## Real input smoke checks

- 0723: collected metadata from 146 JSONL transcripts and prepared the existing triage output as 31 issue jobs. No model was called by either command. Placeholder model labels are kept separately from real model IDs.
- AIPPT Codex generation rollout: session, recorded model/provider and CLI version collected.
- cofi4 DevEco SQLite: selected root plus its 14 descendants, with recorded model/provider/client version. Other roots and account tables were not inspected by the collector.
- Historical migration tool/skill versions absent from source/server metadata remain unknown. Analysis model is not substituted for migration model.

Raw transcripts, generated provenance, investigation jobs and local memory snapshots are not committed to this repository.

## Independent review and regression fixes

The read-only review reproduced identity drift, metadata-pool mismatch, timestamp-only revision noise, invalid historical dates, incompatible documentation examples and partial output on an existing views directory. Each was fixed and covered by regression tests. A follow-up found same-database/different-DevEco-root collisions; the local identity includes the explicit DB root session now.

Follow-up review confirmed that changed evidence preserves card identity and invalidates old lessons; metadata recapture alone does not; withdrawal and transitive dependency invalidation suppress default recall; invalid timestamps, no-checker force and mismatched materials are rejected; and conflicting view output does not leave a card behind.

## Not established by these checks

- No new end-to-end model attribution score or migration-improvement score.
- No measured semantic recall/precision advantage. First retrieval backend is lexical words/CJK bigrams plus directory navigation.
- No production OBS upload, server integration or automatic cross-platform hook installation.
- New multi-target case envelopes are not directly loadable by the old single-target UI. Exported compact views use the existing submission contract.
- `active` is a maintainer-reviewed suggestion, not a machine-certified causal truth. Structural/reference tests are not semantic validation.
