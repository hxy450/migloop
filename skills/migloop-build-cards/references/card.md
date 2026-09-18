# 情景卡模板与封装

一张卡解释一个修复问题，可有多个成因和多条示例链。先完成“相关输入 → 首次可核偏差 → 被修文件”的解释，再填坐标。修复说明、参与者和元数据由job保留，图只声明支撑归因的节点。

## 模型填写

下列占位内容替换为真实材料。多文件可复制graph；同一文件的多个起点放同一graph。

```yaml
title: "本问题名称"
when: "下一次任务行动前能识别的适用情境"
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
- when描述未来任务条件；历史出错时间留在节点。持久ID、模型/平台等元数据由脚本生成。
- 每个job目标有graph或明确未决说明。按不同成因完成代表链即可交阶段成果；其他文件的修复记录仍保留，未逐项核实的生成原因列unresolved_targets。

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

后续稿沿用同一job与pack入口，分别保存`draft-2.yaml`、`case-2.json`；原稿留作复查。

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
