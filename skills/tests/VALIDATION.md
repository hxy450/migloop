# Skill bundle validation — 2026-09-17

The initial 2026-09-17 checks covered skill instructions and scripts only. Later dated checks below include the shared inquiry changes needed by self-contained card validation; they do not deploy the renderer/server or modify global hook configuration.

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
