# V6 alternative-viewer UI verification: 050eed4

Date: 2026-09-09. This is a read-only replay audit, not a new model experiment. Both investigators used frozen `4d5db4f`; the independently frozen viewer is `050eed4`. Original run files and frozen sources were not changed. The layout patch does not change the investigator, ledger contract, tool protocol, verdict, or recorded trajectory.

## Runs and outcome

| Run | Viewer | Steps | Recorded nodes / visits / transitions | Result |
| --- | --- | --- | --- | --- |
| `formal-v6-reference/codex-c4/runs/tools/rep1` | port 19669, sid `01a021e5` | 76 | 4 / 5 / 4 | Geometry, exact document/reason provenance, check display passed |
| `formal-v6-document/member-center/runs/tools/rep1` | port 19670, sid `ff019d8a` | 47 | 11 / 4 / 3 | Geometry, exact document/reason provenance, incomplete coverage and draft mismatch display passed; two pre-existing candidate-read edges have invalid version binding, described below |

`probe_smoke.cjs` and `probe_basis_smoke.cjs` passed on both pages. C4 truthfully reports missing optional basis, rather than inventing one. Member's available basis and its findings-panel copy were compared with the original model fields; expected, actual, counterevidence, and both evidence groups were preserved. The basis helper's selector was scoped to canonical per-node rows, with a separate exact-copy check for per-file findings; this changes only the test helper.

## Geometry and unchanged trace

The test measured every rendered atom and collapsed stub rectangle, not merely DOM counts. At initial 1900×1300 and subsequent widths 1250, 2200, and 1600 (height 1300), there were no overlapping boxes and no boxes outside the fitted graph viewport. Actual stub expansion was also tested:

- C4: 6 boxes (4 atoms, 2 stubs), then 7 boxes (6 atoms, 1 stub) after expanding stub `t5`. The previously hidden `agent:__main__:01a021e5@18` remains visible.
- Member: 14 boxes (11 atoms, 3 stubs), then 22 boxes (20 atoms, 2 stubs) after expanding stub `t13`.

Expansion adds human-requested ledger context, not investigator visits. Exact snapshots of `trajectory`, `steps`, and `evidence_graph` were unchanged after expansion; original recorded node sets were unchanged. Both pages exposed all step IDs 1–76 / 1–47, and check steps did not create visits. No JavaScript exceptions were observed. Original run file-name/SHA256 inventories matched before and after the checks.

| Field | C4 | Member |
| --- | --- | --- |
| trajectory SHA256 | `fbb06f70bd0d12e73ed4c87fa10545bfaa27f56c6391ecd13d8cbd2552dce7c4` | `d6ff2565298b4948f2b7a421d68f94e6883cebe609b4bcb982e56a0070df705e` |
| evidence graph SHA256 | `9856b220b182bdb802a41ac13199175f4c48d973f29d8d34a47fe73bc3bc2c05` | `dd8c03efe6cd866a52d47f0c8fc1fc2d503c18f88a525881f30741dad63c9cf8` |
| document SHA256 | `3251273b1be3698d699788f006389b3d0c8a2d2b4974bd825f3ec4aa63f1a88f` | `cab2b12be8e77aec4a0a427b531e33d3ce4e0f5293a1edf86c15009e44c5424e` |

## Document, findings, and mechanical-check honesty

C4 `structured.raw` exactly matches the original run's `verdict.yaml`; all 3 node reasons match. Source is `checked_draft_ref`, verified for document provenance only, with `semantic_checked=false`. The last actual check (step 76) is matched and mechanically clear. The displayed one-file/one-item findings projection is model-claimed association, not a new semantic verdict. Empty coverage denominator 0/0 is not represented as proof of exhaustive investigation.

Member `structured.raw` exactly matches the original `verdict.yaml`; all 12 node reasons match. Source is `final_inline`, document-verified with `semantic_checked=false`. Both claim and trace identities are bound, which does not certify semantic correctness.

Member's original model notes claim `mechanical_clear`. The viewer correctly retains the contrary mechanical state:

- Final coverage is 7/38 accounted items: 7 versions and 31 missing candidates; `complete=false`.
- The panel says “尚未有效交代 31 项” and “最终稿与最后核查稿不同”. It does not silently clear the final document because the notes claim clearance.
- Step 46's actual `edge_unconfirmed` issue remains expandable: “是它写的,但写者版本是 v2,不是 v3”. Step 47's actual check is mechanically clear for a different checked document, not for the final reduced document.
- The final document hash differs from step 47's document hash `720e6d466bac58ab9c9eb28ae5ff335c7d8759524a4bccbd27396b9c81642ec9`. Check events 46 and 47 remain process events, not version visits.

## Independent semantic boundary failure: conditional read attached to future version

This pre-existing relation issue is not fixed or concealed by the layout-only viewer. The DOM accurately renders the API graph, but two Member candidate-read edges are not justified as version-specific relations:

- `rw-1`: `MemberCenterPage.ets@v16 → agent-a68daf720e780b4c2@v33`, investigation step 31.
- `rw-3`: the same file version → the same agent at v5, investigation step 33.

Their support is `basis=conditional_read`, `observation=null`, without a read-version binding. Supporting actions (including seq 15371, 15395, 15401, 15407; the first edge also includes later seqs through 15681) occurred between 2026-07-26 20:34:15.052Z and 21:23:49.024Z. File v16 was only written by `agent-af0e3d2ae54dbf769@v3`, seq 17294, source `agent-af0e3d2ae54dbf769.jsonl` L34, at 21:46:12.739Z–21:46:12.801Z. Thus these earlier path-level candidates cannot be treated as possible reads of that future version.

`unknown` is not permission to substitute the queried file version. The next relationship implementation should retain the path/action candidate without a version edge unless independent evidence binds a valid observed version/window. The parent and relation owner were notified; no production or frozen-source change was made in this verification. Consequently this audit does **not** certify all Member read/write graph edges as correct.

## New screenshots

- [C4 trace](screenshots/v6-c4-trace-viewer-050eed4.png)
- [C4 basis/check](screenshots/v6-c4-basis-viewer-050eed4.png)
- [C4 after resize and stub expansion](screenshots/v6-c4-geometry-viewer-050eed4.png)
- [Member trace](screenshots/v6-member-trace-viewer-050eed4.png)
- [Member basis/check with mismatch](screenshots/v6-member-basis-viewer-050eed4.png)
- [Member after resize and stub expansion](screenshots/v6-member-geometry-viewer-050eed4.png)

These are new files. Original 4d5db4f screenshots and run artifacts remain available as the baseline; a successful alternative-viewer replay does not retroactively change them.
