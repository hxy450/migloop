---
name: migloop-memory-maintain
description: 将新增、修订或撤回的迁移情景卡融入已有经验库，提炼有适用条件和来源的短经验，维护目录及版本依赖。
---

# 把卡片提炼成经验

输入指定经验库与卡片，输出经验库新版本和变更说明。经验保留 when、description、unless、why、how、check；证据树留在来源卡中。

1. **读取版本并入卡。** 已有库运行 snapshot，新库运行 init。用 ingest 导入卡，或用 withdraw 撤回整卡/指定结论，再读取新的 revision。
2. **比较已有经验。** 用相邻 recall 的 search/read/browse 加 `--all-statuses` 查相关条目。比较使用阶段、适用情境、偏差机制与预防动作：相同则补证，不同则分支，条件内冲突则保留争议。
3. **写提案。** 按下方模板填写短经验，绑定真实 `case + claim + revision`；实际依赖的其他经验列 requires。目录负责导航，每条经验保持一个稳定身份。
4. **审核并发布。** 核对来源是否支持条件和建议，审核完成的标 active，待补的留 candidate，冲突的标 disputed。用 apply 发布；版本冲突时重读并比较变化，重新形成提案。

来源修改或撤回后，检查 impact 给出的受影响条目，复核后再恢复使用。语义审核由本维护任务完成，机械检查负责引用、版本和依赖。

交付新 revision、主要归并理由、更新/退役范围及待复查项。命令在本 skill 目录执行。云端发布和 hook 接入由宿主负责。

## 两个召回字段

`when`写任务阶段＋动作，`description`写该阶段可见的输入特征。两者从卡片的偏差位置和依据提炼；summary/节点留在卡里，经验的why解释机制，how/check给当前动作。

例如：when为“规格提取阶段，描述图片布局约束时”，description为“源布局依赖wrap_content、adjustViewBounds或资源固有比例”。若同一案例还支持实现阶段的另一套动作，可另建实现经验，不把所有阶段笼统归成“迁移时”。

同阶段同情境再比较机制与动作；条件不同保留分支，条件内矛盾保留争议。旧条目没有description时仍可读写，保留原when直到有依据地重写。补齐描述通过正常提案发布，保留身份与版本历史。

## 入卡与查询

```text
python scripts/memory.py init --store STORE
python scripts/memory.py snapshot --store STORE
python scripts/memory.py ingest --store STORE --cards CASE_A.json CASE_B.json --base-revision REV
python scripts/memory.py withdraw --store STORE --case CASE_ID --reason "撤回原因" --base-revision REV
python scripts/memory.py withdraw --store STORE --case CASE_ID --claim recommendation:1 --reason "该建议失效" --base-revision REV
python scripts/memory.py impact --store STORE --id CASE_OR_LESSON_ID
```

已有库从snapshot开始，新库才init。每次写入后取得新revision；仅空库首次入卡可省base revision。snapshot默认返回版本及计数，全库审计时用--full。修订卡沿用原身份，ingest保存版本并标出受影响经验。

比较相关条目：

```text
python ../migloop-memory-recall/scripts/recall.py search --store STORE --query "事前任务条件与偏差机制" --all-statuses
python ../migloop-memory-recall/scripts/recall.py read --store STORE --ids LESSON_A LESSON_B --all-statuses
python ../migloop-memory-recall/scripts/recall.py browse --store STORE --topic ui/text --all-statuses --offset 0 --limit 8
```

维护时包含candidate、disputed及needs_review，留意状态。局部未命中时用同义词、全库或父目录查找；按next续读相关列表，read每批最多24个ID。

## 如何归并

| 比较结果 | 操作 |
| --- | --- |
| 条件、机制和动作相同 | 保留原ID，补来源或澄清正文 |
| 症状相似，机制/动作不同 | 独立经验或可区分的条件分支 |
| 建议相反，适用条件不同 | 写清when/unless |
| 同一条件内冲突 | disputed，保留双方证据 |
| 项目后置需求 | 限定项目/需求条件 |
| 尚无可执行的复用建议 | 留卡作为证据，说明暂不提炼 |

同批多文件属于一次干预，来源数量按实际独立案例理解。主题归类与经验归并分别处理：多个入口可以指向同一稳定lesson。

## 提案模板

```yaml
base_revision: "当前snapshot返回值"
upsert:
  - title: "短经验标题"
    topic: [ui, text]
    when: "任务阶段＋具体动作"
    description: "当前输入中可识别的适用情境"
    unless: ["明确例外"]
    why: "来源支持的偏差机制与适用范围"
    how: ["输出前的预防动作"]
    check: ["可观察的检查方法"]
    evidence:
      - case: "真实卡ID"
        claim: diagnosis
        revision: "所引用卡版本的hash"
      - case: "真实卡ID"
        claim: recommendation:1
        revision: "所引用卡版本的hash"
    requires: []
    status: candidate
retire: []
topic_descriptions:
  ui/text: "文本内容、分段样式、数字与单位"
```

新lesson省略id；更新时填写原id。topic使用最多三层slug路径，按条目增长形成主题。诊断和建议索引来自脚本生成的claims；核对引用的具体主张支持why/how。建议依赖多项来源时分别列出。

requires只填结论真正依赖的其他lesson ID，供失效传播；循环和缺失依赖由脚本拒绝。源卡树无需复制到经验正文。保留原job/card身份；材料搬迁、问题更名或合拆时显式处理身份沿用/替代。

## 审核和发布

| 状态 | 含义 |
| --- | --- |
| candidate | 待审核建议 |
| active | 维护者核对条件、依据、动作和依赖后，可默认召回 |
| disputed | 条件内存在未解决冲突 |
| needs_review | 来源或依赖变动，系统要求复查 |
| retired | 已退役，保留历史 |

upsert可指定candidate/active/disputed；退役用retire，needs_review由失效处理产生。维护者在本任务内完成语义审核，机械检查负责结构、版本、引用和依赖。修复仍按截止时最终保留状态为参照；使用时机写when，适用范围写description/unless。

```text
python scripts/memory.py apply --store STORE --plan PLAN.yaml
```

apply串行发布。遇版本冲突，重读当前状态并比较变化，再形成新提案。卡片内容或claim顺序变化后，旧版本绑定需重新核实；withdraw与依赖失效会让相关上层经验停止默认召回。检查impact，核实剩余依据及全部依赖后再激活。

交付发布revision、增加/更新/退役条目及理由、仍待复查的范围，保留提案。底层快照与HEAD由脚本维护，直接编辑内部文件会破坏版本协议。
