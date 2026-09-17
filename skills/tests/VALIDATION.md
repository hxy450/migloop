# Skill bundle validation — 2026-09-17

Scope: standalone skill instructions and scripts only. No change to `src/`, inquiry, renderer, service API or global hook configuration on this feature branch.

## Four-skill revision (0.2.0)

- Split migration-wide triage from single-issue investigation; their CLI entrypoints reject each other's commands.
- Four packages pass skill-creator's static validator. Installed previous packages are backed up, not discarded.
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
