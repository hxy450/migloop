# Formal cards (0.9.0)

The investigator's YAML and the historical relation checker are unchanged.
`cases.py pack` writes `migloop-case/3` only after the existing template/path
contract passes. Legacy `/1` and `/2` remain readable under their original hashes.

## Persisted shape

The top-level reading order is identity → situation/summary → recommendations
and repair changes → graph → unresolved items → technical context/references and
receipt. Serialization order never changes a card revision, node/edge ordering,
or lesson source binding; hashes continue to use canonical sorted-key JSON.

- Identity, migration key, original creation time, title, when, description,
  summary, recommendations, changes, participants and unknown/unresolved targets.
- **One `graphs` list.** Authored nodes keep their key/time/reason/problem.
  `resolved` records the checker identity where it differs, kind and supplemental
  existence basis. Edges keep endpoints and force explanation, with every bound
  operation (relation, operation time, source, strength, evidence references).
  Extra checker nodes/edges stay in this list as `derived`; they are never dropped
  because an array position happens not to match.
- A deduplicated `references` table. Edge/operation indices are local zero-based
  references; model node numbers remain one-based. Distinct source files at the
  same physical line are distinct references.
- `context` pins immutable JSON objects in `sessions/<sha256>.json`. Pool labels,
  source manifests, exact scope and observed environment are independently
  content-addressed, so identical values share storage and different cutoffs do
  not accidentally share an environment. No original transcripts are copied here.
- `check` binds the final graphs and reference table to their successful result
  and kernel fingerprint. It is included in the card revision. This is integrity
  checking, not a signature or certification of natural-language causality.

No duplicate draft, claims prose, machine graph, target inventory, empty error
arrays, UI delivery state, temporary report ID or generated quote_verified is
persisted. `case_format.content/claims/context` are the shared read interface.
`diagnosis` resolves to summary; `recommendation:N` to the Nth recommendation.

## Consumers and transport

Standalone pack/enrich outputs have an adjacent `sessions/` directory. Ingest
automatically copies and checks those objects into `store/sessions/`. Store case
rows contain only identity/version/status/title/claim IDs, not copied metadata.
Reading exports still link to the exact card version; they do not copy evidence.

Server checkpoints and final OBS archives upload context objects before publishing
a card pointer. Resume and UI load retrieve and hash-check the same objects.
The UI's disposable view is rebuilt from the authoring projection and original
session; its graph IDs/layout/cache are not written back into the formal card.
An adapter learning an old force relation does not mutate the original card.

## Explicit migration

`memory.py compact --store OLD --out NEW` requires a new directory outside OLD.
It checks all old cards, preserves authored content and all bound operations,
rewrites exact source versions across historical snapshots, and leaves lesson
text/IDs/semantic versions/statuses unchanged. It does not call a model, rerun
investigation, or promote a failed legacy card. Old stores and Git history remain
untouched. Missing context or hash mismatches stop admission/display with the
specific missing object, never silently invent metadata.
