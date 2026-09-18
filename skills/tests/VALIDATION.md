# Skill bundle validation — 2026-09-17

Scope: standalone skill instructions and scripts only. No change to `src/`, inquiry, renderer, service API or global hook configuration on this feature branch.

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
