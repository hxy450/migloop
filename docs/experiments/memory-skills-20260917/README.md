# Four-skill forward trial

This trial validates the split single-issue card skill, not a new accuracy benchmark.

## Frozen setup

- Model: `gpt-5.6-sol`, reasoning `high`, one new Codex CLI thread. No fork/resume, no automatic retry, no parent follow-up hints.
- Issue: the previously triaged 0723 task `会员中心价格数值与后缀样式不一致`, copied without rewriting its observation, changes, questions or participants. Choosing a known difficult issue is not random sampling.
- Prompt: only the build-cards skill path, full transcript directory, and the current-directory `job.json`. No expected author, cause, answer, scores or hidden reference report.
- Investigation: free local raw inspection; an independently imported inquiry index is available as runtime data. No MCP server is enabled in this trial. Packaging uses the unchanged inquiry checker via `pack --db`.
- Scope: one issue, not the whole MemberCenterPage repair inventory. Final retained historical state is treated as the correct target, per the product assumption.
- Isolation: host skills, project instructions, memories, plugins, hooks, web and additional models are disabled per run. Code, skill, task and transcript hashes are checked after execution. This is input/recording isolation, not a claim of OS-level read isolation from all local files.
- Evidence: first and later drafts, native transcript, exact command/configuration, checker receipts and final result are retained. Mechanical success does not certify the semantic attribution.

## Reproduce

Use a new output directory. The launcher refuses to overwrite an old run.

```text
python -B -X utf8 docs/experiments/memory-skills-20260917/run_card.py prepare --out NEW_OUTPUT --tasks EXISTING_REPAIR_TASKS.yaml --title "会员中心价格数值与后缀样式不一致"
python -B -X utf8 docs/experiments/memory-skills-20260917/run_card.py run --out NEW_OUTPUT
python -B -X utf8 docs/experiments/memory-skills-20260917/run_card.py verify --out NEW_OUTPUT
```

Local runs: `C:/Users/hongy/projects/_migloop-four-skills-trial-20260917/sol-0723-price-v1/` and `sol-0723-price-v2/`. These are two independent runs of **one issue**, with one generic skill revision between them, not two independently sampled test cases. See [semantic review](review.md).

The parent reviews historical input receipt, actual output content, retained repair and causal propagation independently after the model run. No reviewer correction is fed back into this frozen run. Report semantic findings and mechanical checks separately; do not turn one task into a percentage score or reuse an earlier 27/28 result for this new workflow.
