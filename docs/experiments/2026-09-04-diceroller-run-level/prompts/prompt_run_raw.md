{common}

## 你手里有什么

当前工作目录里是这份实录的原始转录:

- `<sid>.jsonl`:各会话的主转录。Claude Code JSONL,每行一条记录:`type` 是 user / assistant,`message.content` 里是
  text / tool_use / tool_result 块,`timestamp` 是时刻,`uuid` 是记录号,`attributionSkill` 是管线阶段戳(不一定有)。
- `<sid>/subagents/agent-<id>.jsonl`:该会话派出的子代理转录,同目录 `agent-<id>.meta.json` 是它的描述;
  主转录里 Task 工具的 tool_result 带 `toolUseResult.agentId` 可以对上。
- `stage-marks.json`:阶段时间表 `marks: [{stage, ts}]`。

Read / Grep / Glob / Bash(只读)随你用。单个主转录可达 10MB,先 grep 定位再按行读。
