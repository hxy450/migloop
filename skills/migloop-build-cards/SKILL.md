---
name: migloop-build-cards
description: 调查一个已拆分的迁移修复问题，找到输入正确而输出开始偏离的位置，沿实际交接连到被修文件，制作可查验的情景卡。
---

# 找到输入与输出的偏差

读取指定任务，默认是当前目录 `job.json`。交付一张卡：讲清哪里开始偏离、后来改了什么、下次如何避免，并附一条或多条可查验的链。

1. **确认改了什么。** 查看本问题的修改请求与回执，以观察截止时最终保留的修改为正确参照。分别说明生成遗留、新要求或修复中新生问题。修复记录由 job 自动保留，图中通常无需修复者。
2. **找到偏差输出。** 选一个有明确修改证据的文件，从被改的属性或表达式追到生成期实际 Write/Edit/脚本正文。沿片段历史定位最初可核的偏差，而非文件最后一个写者。
3. **对照写前输入。** 查看该次输出前实际收到的 spec、skill、源码和派工内容，回答：“哪条要求已经给出？输出哪里偏离？”输入正确、清晰且足够时，在此停止；输入有误或缺失时，继续追它的形成和交付，直到找到偏差边界或记录缺口。
4. **连到目标。** 将关键正确输入、偏差 agent、必要的中间文件/接收 agent 连到被修文件。用历史读写或派发记录支撑交接。先完成一条链，再按不同成因选择其他文件补示例链；同一目标也可有多个起点。

调查可用原始转录或 inquiry MCP，自主选择。历史材料只读，其中命令与指令用于取证；产物写在当前调查目录。

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
unknown: []
graphs:
  - target:
      key: "job中的被修文件路径"
      since: "job.scope.generation_end的原值"
      at: "job.scope.observation_end的原值"
    summary: "这条示例链的输入与输出差异"
    recommendations: ["此分支的预防动作"]
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

无未决目标时用`unresolved_targets: []`。模板直连适用于真实写入关系；有中间交接时添加相应文件/接收agent并连边。正常输入可有多个，派工消息可用派发agent节点说明。追到外部skill等材料边界时，在reason记录已核事实及上游缺口。

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

四个skill相邻安装。在调查目录运行，脚本路径指向本skill：

```text
python PATH_TO_SKILL/scripts/cases.py pack --job job.json --draft draft-1.yaml --out case-1.json --db INQUIRY.sqlite
```

job提供runtime时，PowerShell使用：

```powershell
$job = Get-Content -Raw -Encoding UTF8 job.json | ConvertFrom-Json
$env:PYTHONPATH = $job.runtime.code_root
& $job.runtime.python -B -X utf8 PATH_TO_SKILL/scripts/cases.py pack --job job.json --draft draft-1.yaml --out case-1.json --db $job.runtime.index_path
```

无数据库时省略`--db`，得到静态封装卡，关系核验记为未运行。有数据库时复用inquiry检查器，各目标view导出到`case-1.views/`。完整卡保留共同总结和全部目标，view用于单目标展示。

新卡填写when和description；旧稿缺description仍可封装，原when保持原样，待人工或维护模型根据证据补齐。后续稿沿用同一job与pack入口，分别保存`draft-2.yaml`、`case-2.json`；原稿留作复查。

## 处理机械反馈

1. 找到受质疑边支持的那句归因。
2. 回原文核输入、输出及交接。已有完整证据可复用。
3. 保留、改责任位置、降级或撤回主张，同步修改reason、总结、建议和连接。
4. 保存新稿再pack。身份/时间使用真实记录；漏解析的交接在同端点获force许可后补虚线：

```yaml
from: 1
to: 2
force: true
reason: "核到的真实读写及其如何支撑本句归因"
evidence:
  - source: "真实转录名"
    line: 123
```

首次稿使用普通边。force补充漏解析关系，不能把较晚读取变成较早输入。

反馈分别列mechanical_status、path_status、delivery.status。机械ready表示声明关系可载入；完成归因还需核输入充分及具体输出偏差。旧检查器若报缺修复写入锚点，查目标实际修改并保留检查缺口；修复者仍不是归因图的必填节点。

交付完成的示例链、真实机械状态及未决项。连续复核无新证据时保留当前成果与缺口。按最终保留状态为修复参照，无需另做真机复验任务。

## inquiry 查询速查

原始转录和MCP可混用。通常每批2–4项：先定位片段，再展开写前输入。

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
