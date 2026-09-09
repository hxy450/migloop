# Formal-v4 C4: source-stratified search

Decision before the next model call: run C4 once with a new frozen source, the exact Formal-v3 task/pool, GPT-5.5 / medium / native MCP, 1800 seconds, no retries or gold-answer hints. Preserve v3 outcomes.

The specific source change partitions full-pool matches into tool outputs, tool inputs, statements, instructions and other records. Each bucket shows its earliest match, count and raw action pointer. A system prompt mentioning a command no longer suppresses the first matching output. No bucket is labelled semantically true; failed outputs are not skipped in favour of success. All hits remain counted and expandable via agent-scoped search.

Hypothesis: the investigator more reliably finds direct validation output rather than only later claims, without turning any later build into proof that it contains the patch or validates behaviour. Apply the unchanged bounded reference and report missing native evidence as a separate issue. Costs may rise: extra source previews add text. Measure calls, tool characters, wall time and both total/uncached input; no n=1 general efficiency claim.

This snapshot also includes the separately tested integer-until disclosure fix, explicit invalid-version rejection in HTTP, non-navigable tail-reader slots and clarified generic role wording. Hence this is a bundled iteration, not a causal estimate of source grouping alone. The preceding runs did not use integer until; their errors cannot be explained by that bug. Neither reference answers nor case-specific build markers/coordinates enter tool instructions.
