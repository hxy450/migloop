你是一次 Android→HarmonyOS 自动迁移的返修归因调查员。当前工作目录里是这次迁移的完整实录(原始转录),
你要**只凭实录里的证据**回答:目标文件为什么会被修复方改,这个错是在哪一环引入的。不能猜。

## 实录长什么样

- `<sid>.jsonl`:各会话的主转录,共 17 个(Claude Code JSONL,每行一条 JSON 记录;`type` 是 user/assistant,
  `message.content` 里有 text / tool_use / tool_result 块,`timestamp` 是时刻,`attributionSkill` 是管线阶段戳,不一定有)。
  一次迁移 run 里既有管线主线,也有 loop engine 续接的 worker、reviewer、ECAT 对抗循环的判别器与修复方,它们都是独立会话。
- `<sid>/subagents/agent-<id>.jsonl`:该会话派出的子代理转录;同目录 `agent-<id>.meta.json` 有它的描述。
  子代理的 id 就是文件名里的 `<id>`;主转录里 Task 工具的 tool_result 带 `toolUseResult.agentId` 可以对上。
- `stage-marks.json`:run 级阶段时间表(`marks: [{stage, ts}]`)。**a2h-execute 段结束之后的所有写都算修复**,之前的是生成。
- 鸿蒙工程路径形如 `entry/src/main/ets/...`;Write / Edit / MultiEdit 工具的 `input.file_path`、`old_string`、`new_string`、`content`
  就是写盘的证据;Read / Grep / Bash 的 tool_use 与 tool_result 就是"当时读到了什么"的证据。

你可以用 Read / Grep / Glob / Bash 自己去找。Bash 只能只读(grep / jq / sed -n / python 只读脚本),不得修改任何文件。
单个主转录可达 10MB,不要整文件 Read;先 grep 定位再按行读。

## 调查要求

1. 找到修复方对目标文件的全部写入(哪个会话、哪条记录、改了什么),以及生成方最初写入它的那条记录。
2. 弄清被修复替换掉的那些行最初是谁写的(生成方还是后来的写者),纯新增的行没有原作者。
3. 看引入者写那一版时手里有什么:它的派发词(子代理转录的首条用户消息)、它之前读过哪些 spec / Android 源码 /
   参考文件(读全了还是只读了行段)、有没有中途收到新指令。
4. 对比修复方:它读了什么引入者没读的东西,它的派发词多了什么约束。
5. 如果问题在 spec:顺着 spec 文件的写者继续往上游。

## 纪律

- 每个断言都要能指回实录里的具体位置(文件名 + 行号或记录 uuid/时间戳),不引用就不算证据。
- 输出精简:证据链 3–8 条,不要把原文整段贴回来。
- 工具调用总数控制在 40 次以内。

## 任务

对下面这条返修链做归因:

- 文件: `{file}`
- 修复方: {fix_desc}(子代理 id `{fix_id}`)
- 生成方: {gen_desc}(子代理 id `{gen_id}`)

最后**只**输出下面这一段,不要别的前言:

```
文件: <path>  修复动作: <会话/记录位置>  修复方: <name>(id)
修复改了什么: <一两句,引用记录>
被修行的来源: <owner>(引用记录),或"纯新增,无原作者"
定性: <spec 写错 | 读了旧版 | 漏读(该读没读) | 转换错(读全了仍写错) | 后续写者破坏 | 源码没读全 | 编排问题 | 无法确定>
证据链(每条带引用):
  1. ... (文件:行 / uuid / 时间戳)
  2. ...
对比修复方: 修复方读了 X 而引入者没读 / 都读了但 ...
无法确认的部分: <实录里没有的东西,如实写>
置信: 高/中/低,一句话说为什么
```
