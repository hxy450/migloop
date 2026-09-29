# Codex 原生命令读取适配（2026-09-29）

## 原因

真实 DiceRoller 使用 code mode：外层 `exec` 调用之外，运行时另发
`event_msg / item_completed / CommandExecution`，其中记录 command、cwd、
parsed_cmd、stdout、stderr、exit_code 和 thread_id。
inquiry adapter 之前只接了同级的 FileChange，漏接 CommandExecution。
普通 MigLoop 报告的审计识别成功，不等于 inquiry 文件读写关系完整。
旧跨平台契约测试里的 Codex read_file 简化样例未覆盖这一真实协议。

## 实现边界

- Codex adapter 解码运行时执行事件，不从 exec 的 JS 字符串里制造调用。
- 每个原生命令保留一个调用与回执；额外读取投影复用同一事件和原文坐标。
- 通用 Store 消费 read_observation，不包含 Codex 分支；网页、CLI、检查器共用索引。
- 原生 parsed_cmd 是语法标记，不单独当执行证明。首批确认范围为 cat、sed -n 数字范围 p、
  head/tail，允许顺序连接及无副作用的输出/列表命令。须有成功完成、exit_code=0、
  空 stderr、返回文本，且文字命令路径与原生 read 标记一致。
- 条件分支、变量、管道、重定向、脚本和目录切换暂不认证文件读取，原命令回执仍可查看或供 force 引用。
- 路径按此次执行 cwd 解析（包括 file URI），不误用会话初始目录。
- 按完成回执时刻建立关系，不猜请求开始时间，不把未来返回放进过去输入。
- 外来 thread_id、缺失时刻/调用 ID、重复且无法唯一配对的回执不产生确认关系。
- 多文件命令保留合并输出，页面注明不是当前文件的独立全文。

## 回归

新增真实协议形状的净化 fixture，覆盖正常输入 → 偏差 agent → 文件的普通边机械检查、
查询原文、时间边界、多文件输出、失败与未知状态、路径及 owner、防引用文本伪造。
旧式 function_call/Read、FileChange 写入和 Claude/DevEco 协议保持不变。
