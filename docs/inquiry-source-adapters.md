# Three native sources, one inquiry kernel

`source_adapters/{claude,codex,deveco}.py` decode native identity, message roles,
tool requests and returns. `tool_contracts.py` decodes literal native file-tool
contracts once. Store, card checker, CLI/MCP and web original/diff views all use
this same registry. No source-platform field is added to model-authored cards.

| Source | Input | Identity / original coordinates |
|---|---|---|
| Claude Code | native JSONL | sessionId + agentId; original line/block |
| Codex | native rollout JSONL | session_meta.id; original line/call_id |
| DevEco | native export or selected SQLite session tree, frozen as event JSONL | native session/message/part/callID, plus exported line |

DevEco preparation (read-only source, explicit scope):

```powershell
$env:PYTHONPATH = 'src'
python -m migloop.inquiry.source_adapters C:/path/deveco.db --session ses_ROOT --out C:/new/frozen-pool
python -m migloop.inquiry --db C:/new/index.sqlite import --pool C:/new/frozen-pool
```

The exporter also accepts native `{info,messages}` JSON files or a directory of
these exports. A DB export requires a root ID and includes only its descendants.
It reads a single SQLite transaction, opens mode=ro, and refuses to overwrite.
Requests contain native input and start time, not later output. Results retain
the full native part and completion time. Missing timestamps stay unknown.
`origin` retains session/message/part IDs and a native-part content hash. These
JSONLs are explicitly labelled projections, not original Claude transcripts.
Card provenance fingerprints the full exported contents, including tool returns.
The old DB-header-only metadata collector does not certify a card: export first.

The index records platform and native parent metadata separately. A parent hint
does not manufacture a dispatch edge; an actual paired dispatch call is required.
Shell/JS wrapper calls remain opaque. Literal paths can populate navigation but
do not certify file effects. A script relationship still needs the existing
feedback/force protocol, anchored to a real call. Native apply_patch is decoded
only at native tool positions; text that merely mentions a call is never executed.

Index schema 6 requires cache rebuilds. Evidence handles for unchanged native
records remain byte-addressed; old indices must be opened with their frozen code.
Release construction and runtime fingerprinting recursively include the adapters.
The server vendors this release; do not maintain another decoder in the server.

Source platform is independent of analysis execution. Reading Codex/DevEco does
not imply running those CLIs for analysis; the current server analysis worker is
still the existing Claude CLI with a configured model.
