# 维护格式与命令

把卡片事实提炼为有适用条件的短经验；目录提供渐进式导航，证据树保留在卡片。所有命令在本skill目录运行。

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
    when: "下一次任务行动前能知道的条件"
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

upsert可指定candidate/active/disputed；退役用retire，needs_review由失效处理产生。维护者在本任务内完成语义审核，机械检查负责结构、版本、引用和依赖。修复仍按截止时最终保留状态为参照；适用性与泛化范围写进when/unless。

```text
python scripts/memory.py apply --store STORE --plan PLAN.yaml
```

apply串行发布。遇版本冲突，重读当前状态并比较变化，再形成新提案。卡片内容或claim顺序变化后，旧版本绑定需重新核实；withdraw与依赖失效会让相关上层经验停止默认召回。检查impact，核实剩余依据及全部依赖后再激活。

交付发布revision、增加/更新/退役条目及理由、仍待复查的范围，保留提案。底层快照与HEAD由脚本维护，直接编辑内部文件会破坏版本协议。
