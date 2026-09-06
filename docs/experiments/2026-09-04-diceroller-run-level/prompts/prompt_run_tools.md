{common}

## 你手里有什么

这份实录已被整理成一本账,MCP 服务器 `migloop` 提供只读查询工具,每个工具的 `sid` 参数填 `{sid}`:

- `guide`:账本的模型、各种标记的含义、各工具的说明。先读一遍。
- `sessions`:execute 结束后被改过的工程代码与配置文件清单:每个文件被谁在什么时候改了哪几版、生成方是谁、被改的行原来是谁写的。
- `index`:账本目录,全部 agent 与文件各一行,可按类型和关键词过滤。
- `file`:某文件某一版:历次写者、读过这一版的 agent、内容、diff。
- `agent`:某个 agent:派发词、收件箱、逐版的读写、收尾输出。主会话很长,用 `v` / `since` 取窗口。
- `blame`:某文件某一版逐行是谁写的;`changed=True` 只看这一版替换掉的行。
- `diff`:某一版的 diff。
- `action`:某次工具调用的完整原始输入与输出。

原始转录也在当前工作目录:`<sid>.jsonl` 是各会话主转录,`<sid>/subagents/agent-<id>.jsonl` 是子代理转录,
`stage-marks.json` 是阶段时间表。Read / Grep / Glob / Bash(只读)随你用。
