# 经验维护协议

本协议覆盖“既有 memory + 新增/修订/撤回卡片 → 模型归并提案 → 机械检查与版本发布”。历史卡是依据，短经验是建议，目录是检索入口；三者不能互相代替。

## 命令与写入边界

```text
python scripts/memory.py init --store STORE
python scripts/memory.py snapshot --store STORE
python scripts/memory.py ingest --store STORE --cards CASE_A.json CASE_B.json --base-revision REV
python scripts/memory.py withdraw --store STORE --case CASE_ID --reason "撤回原因" --base-revision REV
python scripts/memory.py withdraw --store STORE --case CASE_ID --claim recommendation:1 --reason "仅此建议失效" --base-revision REV
python scripts/memory.py impact --store STORE --id CASE_OR_LESSON_ID
python scripts/memory.py apply --store STORE --plan PLAN.yaml
```

按实际 `--help` 使用额外筛选参数，不猜协议。init 只用于新库；已有库从 snapshot 开始。更新写入必须使用当前 base revision，只有空库首次导入卡片可省；每次 ingest、withdraw 或 apply 后重新取得 revision，不能沿用写入前的值。不要直接修改 store 内部文件来跳过版本或依赖检查。

snapshot 默认仅返回当前版本和计数，避免维护者也被全量经验淹没；用 browse/search 查相关条目。只有明确审计全库时才加 `snapshot --full`，该模式完整展开而非静默截断。

ingest 只接收卡并处理已记录依赖，不会从相似文字自动生成、合并或批准经验。修订必须沿用该卡身份，不能另造 ID 规避历史版本。withdraw 撤回整卡；带 --claim 时只撤回指定结论，不改写 CASE.json 的 status。原始卡版本和撤回记录保留可查。依据不再成立时，通过反馈和 impact 查看受影响经验，再决定修订、退役或继续待查。

## 比较已有经验

用相邻 skill 的脚本读取同一经验库：

```text
python ../migloop-memory-recall/scripts/recall.py search --store STORE --query "当前卡的事前任务条件与机制" --all-statuses
python ../migloop-memory-recall/scripts/recall.py read --store STORE --ids LESSON_A LESSON_B --all-statuses
python ../migloop-memory-recall/scripts/recall.py browse --store STORE --topic ui/text --all-statuses --offset 0 --limit 8
```

默认生成期查询只有 active；维护查询均带 --all-statuses 找到 candidate、disputed、needs_review 等记录，并留意状态。搜索不到时改用任务动作、源码名和同义词，或浏览父目录；不要把一次关键词无结果当成“库里没有”。browse/search 用 --offset 和 --limit 分页，read 每次最多 24 个 ID，超出时显式分批。响应有剩余项时继续读取相关范围。

| 证据与条件关系 | 维护决策 |
| --- | --- |
| 适用条件、机制和动作一致 | 给原经验补来源或澄清正文，保留 ID |
| 症状相似但原因或动作不同 | 保留独立经验，或写清可判别的分支 |
| 建议相反但条件不同 | 保留条件与例外，不抹平差异 |
| 相同条件下相互矛盾 | 标 disputed，保留双方来源，不按频次投票 |
| 仅为后置产品要求 | 限定项目/需求条件，不包装成普遍生成错误 |
| 材料只能支持个案，无法得出可执行建议 | 不新增经验，记录处理理由 |

“放入同一主题”是归类，“共用一个 lesson 正文”才是归并。一个批量脚本修改多个文件是同次干预，不能当成多个独立成功样本。不能因只有一张卡就断言经验无用，也不能因卡多就声称泛化已证。

## 提案形状

```yaml
base_revision: "snapshot 返回的当前 revision"
upsert:
  - id: "已有 lesson 的 ID；新建时省略这一项"
    title: "保留带局部样式的文本差异"
    topic: [ui, text]
    when: "从带局部样式的源文本提取规格或实现目标界面时"
    unless:
      - "当前需求明确要求全串统一样式"
    why: "只传最终字符串可能丢失局部样式；适用范围受所引用卡片限制"
    how:
      - "核对分段范围、样式和继承关系，再映射目标实现"
    check:
      - "选择具有不同分段的当前样例，比较各段呈现"
    evidence:
      - case: "入库返回的真实卡 ID"
        claim: diagnosis
        revision: "该卡版本的真实 hash"
      - case: "同一或其他真实卡 ID"
        claim: recommendation:1
        revision: "所引用卡版本的真实 hash"
    requires: []
    status: candidate
retire:
  - id: "确需退役的既有 lesson ID"
    reason: "具体失效或被何条经验替代；没有退役项时 retire 为 []"
topic_descriptions:
  ui/text: "文本内容、分段样式、数字与单位、资源字符串"
```

示例只说明字段。引用真实卡和真实版本；无新增、更新或退役时对应列表用 `[]`。新经验省略 id，由脚本分配；已有经验保留原 id。topic 使用最多三层的 slug 路径；保持浅目录，不为少量经验强行加层。目录路径移动也不改变身份。

`claim` 使用脚本生成的 `diagnosis` 或 `recommendation:1` 等索引，不临时发明 claim 名。diagnosis 来自全卡总结，recommendation 的数字对应全卡建议顺序。详细 graph 节点作为复核依据保留在卡中，不需要复制到经验正文。必须核对被引用主张确实支持 why/how，而不只是与标题相似。

一个建议依赖多张卡或不同主张时显式列全。卡片 revision 绑定当时原文，不能只写 case ID 指向会变化的最新版本。卡片附加新建议、改顺序或更改诊断后，旧绑定也需要复查；不得凭名称自动重绑到新 claim。

`requires` 只用于实际依赖的经验，不把“主题相关”写成依赖。上层条目如果离开下层结论就无法成立，必须列出下层 ID；不能仅在 prose 提到下层，导致系统无法传播失效。不要创建自身依赖、循环或不存在的依赖。

## 条件、证据和状态

when 描述新任务在行动前能知道的条件；unless 写明确例外。why 解释具体机制及证据局限；how 给动作；check 给可观察的验收方法。适用平台、框架和版本范围写进条件，不以元数据缺失直接推断兼容，也不把单个历史数值硬编码为通用做法。

| 状态 | 含义与默认召回 |
| --- | --- |
| candidate | 有依据的待审核建议；默认不返回 |
| active | 维护者已按本次材料审核；生成期默认可召回，不表示系统真值 |
| disputed | 条件内存在未解决的矛盾；默认不作为建议返回 |
| needs_review | 来源或下层依赖变动导致失效，等待复查；默认不返回 |
| retired | 已退役，保留历史；默认不返回 |

upsert 的主动状态只用 `candidate`、`active` 或 `disputed`；`needs_review` 由失效处理产生，退役用 retire 操作。将 candidate 设为 active 前，维护者须核对条件、例外、主张支持、最终保留的修复与依赖。沿用卡片约定：观察截止时最终状态是本次目标，不因缺少修复后运行验证而阻断经验提炼；历史上后来被推翻的修复不能作为最终建议。这个工作约定不代表泛化收益已经实证。无需因“active”字样追加人工审批；用户已授权的维护由模型完成语义审核并如实说明局限。

修改或整卡撤回后，显式绑定它的经验及依赖这些经验的上层条目进入复查，停止默认使用；单条 claim 撤回按明确绑定该 claim 的依赖传播。即便经验还有别的来源，也先核查剩余依据能否独立支撑正文，再决定恢复。系统只能追踪记录过的依赖，不能保证发现模型漏写的隐含依赖。

## 发布与冲突

apply 使用 base_revision 防止以过时 snapshot 覆盖更新。收到版本冲突时重新读取现状，比较冲突经验、卡版本和依赖，再生成新提案。发布串行进行；并行调查可以产出候选，不能同时假定同一旧 revision 有效。

机械校验检查结构、引用存在、版本、状态、依赖及目录可达性。它不能证明输入充分、归因正确、建议有效或没有漏项。检查失败时改有依据的内容；不能把被退役依赖从 requires 删除后保留同一结论来绕过阻止。

报告发布 revision、主要变化、未激活/待复查条目及原因。保留提案与处理理由，目录和短经验来自同一版本。安装或维护本地库不自动配置跨平台 hook、共享其他项目数据或部署服务。
