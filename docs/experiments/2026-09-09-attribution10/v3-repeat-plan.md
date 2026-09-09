# V3 Member repeat: stability diagnostic

Decision recorded after both v3 rep1 reports completed and before rep2 starts. Rep1 showed better scope labels but regressed S4 attribution and incorrectly labelled repair/detection activities as defect introduction. Keep this failure; do not replace it with a best run.

Run exactly one additional Member replicate with the same frozen `source-18b8f7f`, exact task/raw pool, GPT-5.5 / medium / native MCP and 1800-second timeout. No extra feedback or answer hints. Report both replicates regardless of outcome. This is within-version variability, not a test of the follow-up cutoff fix or proof of intervention benefit.

Known source limitation: seq-only `agent(until=...)` can expose a result returning after the cutoff. Neither v3 Member rep1 nor its observed role regression used this parameter. Rep2 must be audited for it and must not receive a clean audit claim if it encounters the bug. The separate working-tree fix is never copied into this frozen source.
