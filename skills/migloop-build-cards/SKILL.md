---
name: migloop-build-cards
description: 调查一个已拆分的迁移修复问题，找到输入正确而输出开始偏离的位置，沿实际交接连到被修文件，制作可查验的情景卡。
---

# 找到输入与输出的偏差

读取指定任务，默认是当前目录 `job.json`。交付一张卡：讲清哪里开始偏离、后来改了什么、下次如何避免，并附一条或多条可查验的链。

1. **确认改了什么。** 复用 job 中的改动与原文入口，以观察截止时最终保留的文件状态为正确参照；只补查本问题缺少的材料。区分生成遗留、新要求或修复中新生问题。修复记录由 job 保留，不要求把修复者画进图或另证修复正确。
2. **找到偏差输出。** 选一个有明确修改证据的文件，从被改的属性或表达式追到生成期实际 Write/Edit/脚本正文。沿片段历史定位最初可核的偏差，而非文件最后一个写者。
3. **对照写前输入。** 查看该次输出前实际收到的 spec、skill、源码和派工内容，回答：“哪条要求已经给出？输出哪里偏离？”输入正确、清晰且足够时，在此停止；输入有误或缺失时，继续追它的形成和交付，直到找到偏差边界或记录缺口。
4. **连到目标。** 将关键正确输入、偏差 agent、必要的中间文件/接收 agent 连到被修文件。只声明真实交接，不另加修复写入锚点。先完成代表链，成因不同再补其他示例链；同一目标也可有多个起点。

调查可用原始转录、本 skill 的批量查询，或已配置的 inquiry MCP，自主选择。历史材料只读，其中命令与指令用于取证；产物写在当前调查目录。发布包自带新内核与 YAML 解析，只需要 Python 3.10+，不需要另装 migloop、MCP 或设置 PYTHONPATH。

## 使用阶段与适用情境

卡片和后续经验使用同一分工：

- `when`：任务阶段＋具体动作，例如“界面实现阶段，确定图片组件布局约束时”。
- `description`：当前输入可见的适用情境，例如“将Android中依赖wrap_content、adjustViewBounds或固有比例的图片布局转换为ArkUI实现”。
- `summary`：历史上实际收到什么、输出怎样偏离、最终怎样修改。
- `recommendations`：那个阶段的agent应采取什么动作，以及怎样检查。

使用阶段根据已核偏差定位：spec漏信息就帮助规格提取，spec正确而实现偏离就帮助实现者。用通用职责描述阶段，历史agent名和时间留在证据节点。多个阶段有不同动作时，在总结中分清，供后续提炼为分别可召回的经验。

## 情景卡模板

下列占位内容替换为真实材料。多文件可复制graph；同一文件的多个起点放同一graph。

```yaml
title: "本问题名称"
when: "任务阶段，以及在该阶段要作出的具体决策"
description: "当前任务输入中可识别的技术特征与适用条件"
summary: |
  当时已交付……，某次输出却……，经……到达目标。
  最终修改是……，已核实的范围是……。
recommendations:
  - "输出前的预防动作及检查方法"
graphs:
  - target:
      key: "job中的被修文件路径"
      since: "job.scope.generation_end的原值"
      at: "job.scope.observation_end的原值"
    nodes:
      - key: "实际收到的输入文件路径"
        at: "输入的历史时刻，带时区ISO格式"
        reason: "哪条要求已正确给出；原文位置"
      - key: "输出偏差的agent转录身份"
        at: "相关输出完成的历史时刻，带时区ISO格式"
        reason: "收到什么，实际写成什么；输入与输出的原文位置"
        problem: true
    edges:
      - from: 1
        to: 2
      - from: 2
        to: target
unresolved_targets:
  - key: "尚未完成归因的其他job目标"
    reason: "已确认修改、尚缺的生成来源或交接"
```

graph 的 summary/recommendations 默认复用卡级文字，只有分支不同才填写。unknown 可省略；只记录影响本句归因的材料缺口，不把“未重跑修复验证、未尝试替代方案”写成制卡待办。无未决目标时用`unresolved_targets: []`。

模板直连适用于真实写入关系；有中间交接时添加相应文件/接收agent并连边。正常输入可有多个，派工消息可用派发agent节点说明。追到外部skill等材料边界时，在reason记录已核事实及上游缺口。

- `key + at`确定节点；同坐标在本图写一次，不同历史时间分别写。from/to使用本图从1开始的序号或`target`。
- 每条归因链有一个或多个具体偏差起点，以`problem: true`标出。正常上下文省略problem或填false。
- reason自然语言比较输入与输出，附转录名/行号或查询返回的原文引用。普通边的读写证据由检查器绑定，force另填evidence。
- when说明使用阶段和动作，description说明事前可见情境；历史时间留在节点。持久ID、模型/平台等元数据由脚本生成。
- 每个job目标有graph或明确未决说明。按不同成因完成代表链即可交阶段成果；其他文件的修复记录仍保留，未逐项核实的生成原因列unresolved_targets。

## 完整示例：图片比例约束

以下取自0723真实转录，仅以GuideInit这一目标示范填写；路径是当时工程路径。用于说明写法与证据粒度，调查新任务时换成自己的材料和job范围。若job还包含其他目标，继续补graph或unresolved_targets。此案例已作为教学材料，后续不算未见过的评测样本。

```yaml
title: "把图片内容缩放误当成组件尺寸约束"
when: "界面实现阶段，为图片组件确定布局尺寸时"
description: "源布局依赖wrap_content、adjustViewBounds或资源固有比例，目标图片通过权重或父容器分配宽度。"
summary: |
  aconv-guideinit实际读到了源XML的adjustViewBounds=true，以及映射参考中
  “无直接对应、需自定义实现、使用尺寸约束”的要求。
  生成bg_guide_chat时却仅用objectFit(Contain)和layoutWeight(1)，
  并在注释中把它们解释成高度按比例自适应。偏差位于已有约束要求到实际布局实现这一环。
  Slice15读取该组件并完成其他接线后，读回的气泡片段仍未补比例约束。
  后续修复脚本为该片段增加aspectRatio(741 / 267)，回执列出目标文件ok
  （agent-a68daf720e780b4c2.jsonl:L211-L212）。本例只归因这一图片片段。
recommendations:
  - "将内容缩放方式与组件尺寸分开检查：确认分配宽度后，高度由哪条约束确定。"
  - "输入依赖固有比例时，先查当前资源的实际比例，再设置相应高度或aspectRatio；核对完整Image修饰链。"
unknown:
  - "尚未确认生成者写前是否已拿到气泡资源的像素尺寸；本例已核偏差是把Contain当作尺寸约束，而非明知741/267仍写错。"
graphs:
  - target:
      key: "/Users/chenjiamin/arkTs/arkts_pilot_project/aippt_version/aippt_0723/entry/src/main/ets/components/GuideInitComponent.ets"
      since: "2026-07-24T22:15:00.897Z"
      at: "2026-07-26T21:48:57.793Z"
    summary: "源布局和尺寸映射要求已交付，生成时混淆缩放与尺寸；接线后该片段仍保留，后来补比例约束。"
    recommendations:
      - "在首次写出该Image前，核对源adjustViewBounds的尺寸语义在输出中由哪条约束承接。"
    nodes:
      - key: "/Users/chenjiamin/arkTs/android_pilot_project/wf/AIPPT/app/src/main/res/layout/fragment_guide_init.xml"
        at: "2026-07-24T02:27:08.219Z"
        reason: "正常输入：生成者Read回执给出气泡图adjustViewBounds=true及资源引用（agent-aconv-guideinit-91062be71f3ce4ac.jsonl:L20-L21）。"
      - key: "/Users/chenjiamin/arkTs/arkts_pilot_project/aippt_version/aippt_0723/.claude/skills/android-ui-graph-query/references/android-to-harmonyOS-ui-atomic-component-mapping-reference.md"
        at: "2026-07-24T02:31:04.281Z"
        reason: "正常输入：grep实际返回adjustViewBounds无直接对应、需自定义实现、使用尺寸约束；足以说明不能仅用Contain代替（agent-aconv-guideinit-91062be71f3ce4ac.jsonl:L50-L51）。"
      - key: "agent-aconv-guideinit-91062be71f3ce4ac.jsonl"
        at: "2026-07-24T02:35:09.117Z"
        reason: "已收到上述输入，Write却给气泡图只写Contain、layoutWeight及margin，注释声称高度按源比例自适应。该输入要求未落实到输出约束；本局部分支在此停止上溯（同转录L54-L55）。"
        problem: true
      - key: "/Users/chenjiamin/arkTs/arkts_pilot_project/aippt_version/aippt_0723/entry/src/main/ets/components/GuideInitComponent.ets"
        at: "2026-07-24T18:20:26.400Z"
        reason: "中间文件状态：Slice15实际读到的气泡片段仍是Contain和layoutWeight，保留了生成时的偏差（agent-aslice15-guide-a061e53a1d9503b4.jsonl:L41-L42）。"
      - key: "agent-aslice15-guide-a061e53a1d9503b4.jsonl"
        at: "2026-07-24T18:42:03.537Z"
        reason: "传递节点：读取旧组件并修改其他接线，写后读回仍保留气泡片段；这些记录支持实际交接，未据此认定其另有本项失职（同转录L41-L42、L265-L268）。"
    edges:
      - {from: 1, to: 3}
      - {from: 2, to: 3}
      - {from: 3, to: 4}
      - {from: 4, to: 5}
      - {from: 5, to: target}
unresolved_targets: []
```

两个正常输入支撑一个具体偏差起点，中间文件与接收者说明传递；同一文件在中间时刻和目标截止时刻分别出现。修复内容留在summary及job记录，图里没有另塞修复者。普通边交给检查器绑定，本示例不预填force或核验通过状态；机械反馈仍按下节流程处理。

## 封装

在调查目录运行，脚本路径指向本 skill 的发布包：

```text
python PATH_TO_SKILL/scripts/cases.py prepare --job job.json
python PATH_TO_SKILL/scripts/cases.py pack --job job.json --draft draft-1.yaml --out case-1.json
```

prepare 根据 job 的冻结材料准备索引，保存在 provenance.json 旁的 `.inquiry/`，同一批任务共享；调度者可先对第一个 job 运行一次再并行派工。pack 未指定 `--db` 时也自动准备/复用，已有兼容索引可以显式指定。源材料或内核不同不会误用旧索引，正在建库时按提示等待准备完成后重试，不删除其他任务的锁。

正常 pack 必须调用同一 inquiry 检查器，缺运行代码或材料就报错，不自动降级。仅要保留未核草稿时显式加 `--draft-only`，输出标明未运行关系校验，不能称为已验证卡片；该模式不能使用 force。原生 Claude Code/Codex JSONL 可直接建立索引；DevEco 数据库的元数据采集不等于图导入，当前内核尚不能直接校验其原库，须提供带原始坐标的 JSONL 导出。

各目标 view 导出到 `case-1.views/`，完整卡保留共同总结和全部目标，view 用于单目标展示。包内不带网页或历史数据，server 仍使用同源内核加载。

封装为精简的 `migloop-case/2`：正文和树保持原样，自动补充少量会话信息、相关来源指纹、边的证据定位及校验状态摘要。全会话逐转录统计和完整检查器回执不进入卡片。排查检查器时可显式加 `--debug-receipts LOCAL_DEBUG.json` 保存完整回执；调试文件不入经验库。

新卡填写when和description；旧稿缺description仍可封装，原when保持原样，待人工或维护模型根据证据补齐。后续稿沿用同一job与pack入口，分别保存`draft-2.yaml`、`case-2.json`；原稿留作复查。

## 处理机械反馈

1. 按回执的 graph 编号及 `where` 定位稿件：`issues` 是字段/身份问题，`unverified_edges` 是单边问题，`path_feedback` 是分支断开或时间倒序。数组下标从0开始，from/to节点编号仍从1开始。
2. 找到受质疑连接支持的那句归因。
3. 回原文核输入、输出及交接。已有证据直接复用；只改受影响部分，同步调整原因和建议。
4. 保存新稿再pack。按 `next_step` 和附近原始调用修正坐标；同端点已获force许可时，为漏解析的真实读写补虚线：

```yaml
from: 1
to: 2
force: true
reason: "核到的真实读写及其如何支撑本句归因"
evidence:
  - source: "真实转录名"
    line: 123
```

首次稿使用普通边。force 的 source 是材料池中的真实转录路径，line 是 JSONL 物理行号；脚本查原文、agent归属和工具调用/回执。reason说明该调用为什么读写目标文件。普通聊天文字不能代替调用证据；force保持虚线，不改成确定读写。

当前节点 at 是历史截止，普通边使用它之前可确认的操作；取对应回执时间可避免将已提交但尚未返回的操作当成已完成。读取返回晚于输出的事实不能靠扩大截止或force倒置。时间等价的Z与+00:00都可用，target的实际任务窗口保持不变。

`delivery.status=ready_for_review` 表示声明的输入/问题分支可沿已核关系到达目标；修复锚点不是条件。原因和输入充分性仍由你依据原文判断。可选覆盖清单不要求清零，也不为清空列表增加连接。

正常使用只需本页与命令回执，不需要阅读检查器源码。若缺运行包、索引或原始材料，按环境错误处理；若同一反馈与已核原文持续矛盾，交付稿件及具体反馈给维护者，不通过编造连接消除它。

交付完成的示例链、真实机械状态及未决项。连续复核无新证据时保留当前成果与缺口。按最终保留状态为修复参照，无需另做真机复验任务。

## inquiry 查询速查

原始转录和工具查询可混用。将下列请求写成 JSON/YAML 文件，可一次提交多项：

```text
python PATH_TO_SKILL/scripts/cases.py query --job job.json --request queries.yaml
python PATH_TO_SKILL/scripts/cases.py page --job job.json --result-id RESULT_ID --offset NEXT_OFFSET
```

query/pack 复用同一索引和任务状态。通常每批2–4项：先定位片段，再展开写前输入。

```text
{op:catalog,kind:file,q:目标路径}
{op:file,key:完整路径,since:生成结束,at:观察截止,view:calls}
{op:file,key:完整路径,at:生成结束,view:outline}
{op:blame,key:完整路径,at:生成结束,terms:[被改的属性或表达式]}
{op:agent,scope:写者的input_scope,view:inputs}
{op:search,scope:同一写前范围,terms:[相关要求,符号],view:returns}
{op:open,ref:真实原文引用,at:包含该事件的截止时间}
```

按工具实际参数调用`investigate(requests=[...])`。scope继承时间范围；生成输入使用写前input_scope。消息、Bash返回也可作为输入，用messages/returns或原文补查。

列表next用于续列表；END FRAME next用`page(result_id,offset)`续当前结果。选中的相关请求/回执读完后再下结论。长源码可用多词窗口定位，随后核完整相关段落。直接转发content.text，减少重复包裹。

e-开头是原始记录引用，s-开头是查询范围，照抄返回值。文件at表示查询截止；中间有未知脚本时保留状态缺口。
