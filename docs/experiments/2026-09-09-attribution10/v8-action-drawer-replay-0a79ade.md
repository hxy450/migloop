# V8 action drawer fix: frozen-viewer replay

2026-09-09. Original investigator/source remains **b540cb2**; viewer is frozen **0a79ade**, port **19676**. The changing v2 worktree was not used. Original run: `formal-v8/member-center/runs/tools/rep1`.

All **18 actual action(ref) steps** were clicked and their original input/output drawers loaded (HTTP 200), including tail steps **#16/#23/#24/#26** with no version. Every click preserved `XT.root`, evidence mode, graph node IDs and the complete recorded trajectory/step/evidence objects. No version or visit was created, and no action drawer offered a reroot button. Normal and tail actions therefore share the fixed raw-record path; it no longer opens the whole agent.

The probe's full steps, trajectory, evidence graph and original model document were compared with the unchanged b540cb2 viewer. The original run-file inventory was unchanged before/after all interactions. Geometry remained non-overlapping and inside the viewport at initial size, after all 18 clicks, after widths 1250/2200/1600, and with the candidate toggle both ways. No JavaScript exception was observed.

The drawer explicitly separates the investigator's recorded query parameters from the current human expansion of both original input/output sides. This is not evidence that the model received or read both sides.

The [screenshot](screenshots/v8-fixed-0a79ade-member-reference-rep1-geometry.png) was visually inspected and shows actual tail step #16 open while the original evidence graph remains intact. The [machine report](v8-action-drawer-replay-0a79ade.json) lists all 18 selected step/action coordinates.

The original finding and screenshots in [the b540cb2 audit](v8-member-ui-verification.md) remain unchanged. No model was called and no frozen source, pool or original run was edited for this replay.
