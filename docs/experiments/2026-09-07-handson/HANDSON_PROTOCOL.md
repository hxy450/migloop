# 亲手调查规程(给子代理)

你在评测一套「迁移返修归因」查询工具。目的不是写出漂亮的报告,是**用工具把一条返修链追到头,并记录工具哪里不顺**。

## 怎么调工具

只用这一条命令(不要读转录文件,不要 grep,不要看仓库代码):

```
"C:/Users/hongy/projects/migbot-elite/.venv/Scripts/python.exe" "C:\Users\hongy\AppData\Local\Temp\claude\C--Users-hongy-projects\f1292ab7-8fba-4df0-bde3-a5b1e7f2d2dc\scratchpad\exp\call.py" <tool> k=v k=v … [--max=N] [--from=文本]
```

先运行 `call.py guide` 读工具说明。工具:sessions(path=文件名) / file(path=, v=, content=1, diff=1, readers=1, start=, n=) /
diff(path=, v=) / blame(path=, v=, changed=1) / agent(id=名字或id, v=, since=, reads=0/1, seen=0/1) /
search(q=, agent=, v=, since= 或 since_ts=, until_ts=;或 file=, v=) / action(id=, seq=) / index(query=, kind=agent|ets|spec)。
`--max` 控制打印字数(默认 6000),`--from="## 逐版时间线"` 从某一节开始打印。每次调用前先想清楚要问什么。
会话固定为 `SID`(见下),call.py 里已写死,不用传。

## 任务

文件 `FILE` 在修复轮被改过。从被改的代码往回追,每一环写清楚「谁、凭什么、判定」,判定只有三种:
传递(照上游做的)/ 错(有好的输入没用或用错)/ 缺(输入里本来就没有)。一直追到池外输入、批量生成的脚本、或技能定义为止;
停在中间要说明为什么停。最后指出问题从哪一环进来,以及**修复侧比生成侧多看到了什么**。
每个断言指回工具坐标(path@v / agent vK / #n@L行)。工具调用尽量不超过 30 次。

## 交付(写到指定文件,两段)

第一段:链报告
```
环 1  …(谁、凭什么、坐标)   判定:…
环 2  …
…
故障进入点:环 k,因为 …
修复侧多看到的:…
无法确认:…
```

第二段:工具体验日志(这一段最重要)
- 逐次调用:序号、调用、返回字数、有用/没用/有误导,一句话
- 卡住的地方:想问什么、工具答不了或答歪了、你是怎么绕的
- 多余的部分:哪些返回内容你根本没用
- 缺的部分:你想要但没有的查询或字段
- 你觉得该改的三条,按重要性排
