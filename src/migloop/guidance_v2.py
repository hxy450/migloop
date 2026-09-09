"""V2 authoring contract; no new investigation atoms or inferred graph edges."""

VERDICT = """\
## 结构化结论 v2
输出一个完整 migloop-verdict/2 YAML 草稿交 check。reason/boundary/notes/recommendation 等自由文本用 `|-` 块字符串；坐标/引用加引号。不必再抄调查路线，系统保留原始调用。

三种声明分开：target_file 是本条讨论的文件范围，不是修复事实；nodes 描述真实 file@v/agent@v 状态；event_claims 描述真实原始动作，尤其未产生正式版本的脚本/尾后动作。事件不是第三种图原子，不把最近版本借来标红。
进入点应定位具体进入事件；早期决策可以解释较晚累计状态，但不能因此把较晚效应版说成最初进入点。check 的坐标对账只提示这个区别，不替你判定原因。

```yaml
schema: migloop-verdict/2
ledger: <照抄 sessions 的账本身份>
root: "file:<真实路径>@v<N>"   # 或真实 agent@v；无合法根可省，不造版本
defects:
  - id: A
    title: <简短变化或问题短语>
    target_file: <本项调查文件的路径，不带@v>
    # repair 可省。仅有明确真实版本时才写；不为分组借最早/最终版包住候选脚本。
    repair: {before: "file:<路径>@v<N>", after: "file:<路径>@v<M>", evidence: ["#标识:n@L行"]}
    entry: []                 # 真实版本节点的进入点；事件进入点用entry_events
    nodes:
      - node: "agent:<真实id>@v<K>"
        role: 进入·错          # 正常 / 带病传递 / 进入·错 / 进入·缺 / 无法确认
        reason: |-
          此版本当时具体哪里不满足已适用要求；不是因它后来参与修复而归罪。
        evidence: ["#标识:n@L行"]
        basis:                # 红色归因填写；正常/无法确认不用凑字段
          expected: |-
            当时适用的具体要求或应保持行为。
          expected_evidence: ["#标识:n@L行"]
          actual: |-
            此节点的实际实现差异。
          actual_evidence: ["#标识:n@L行"]
          counterevidence: |-
            核过的反证、是否只是发现或正确修复、剩余未知。
    # 没有事件主张就省略。event逐字复制action引用，不填anchor/version。
    entry_events: [E1]
    event_claims:
      - id: E1
        event: "#标识:n@L行"
        role: 无法确认
        reason: |-
          这次动作做了什么、结果证明什么和不证明什么。
        evidence: ["#标识:n@L行"]
        # 红事件也填同样basis；位置存在或成功退出不认证效应/因果。
    # edges可省；只声明能核对的版本间读/写/派发，事件不得充当边端点。
    edges: []
    boundary: |-
      停在哪、为什么、哪些证据未看或未知。
    recommendation: |-
      由本条证据支持的可执行改进；不要把现象换词当根因。无依据可省。
coverage:
  manifest_sha256: <照抄 sessions 清单的 MIGLOOP_COVERAGE_RECEIPT.manifest_sha256>
  reviewed:                  # 只写有具体判断的项；可为[]
    - node: "file:<路径>@v<M>"  # 或 candidate: "candidate:<20位摘要>"，二选一
      status: explained      # explained / unresolved / out_of_scope / not_repair
      defects: [A]
      reason: |-
        本项具体改了什么，为什么归到该缺陷，或实际调查后仍不知道什么。
      evidence: ["#标识:n@L行"]
  complement: not_investigated
notes: |-
  后置验证、总体边界或简短总结。
```

模板是形状示例，不要求制造任何节点或事件。nodes 可以[]；entry/entry_events只能指本条相应节点/事件，无法定位就保留未知。
coverage补集由系统根据同一账本、目标和清单摘要展开为“未调查”，不是模型逐项看过、题外、非修复或解释正确。清单不在/有错误时coverage可省并明确边界，不能捏造摘要。有依据的题外改动才逐项写out_of_scope；not_repair须有非修复依据。
实际有原始脚本及结果而没有正式版本：用event_claims陈述可核效应及未知；别把未立版本等同没写。反过来，报告里自称改了只证明说过，不代替执行。
节点或事件标进入·错前，实际打开相关生成前输入与生成实现；索引和后来读回不单独证明当时输入。窗口之外的证据可作后置验证/反证，不能替代该窗口的已知状态。
标缺时披露截时查询范围、未知内容和缺失记录；零命中不证明不存在。后加要求/质量门禁不自动是生成遗漏。

## 提交前核查
check(sid,draft=完整YAML,file=目标文件)只核身份、结构、坐标/引用/显式边、事件定位与清单，不核原因真假，也不算打开节点。
根据诊断补查或改正错误；不能为了清零删真实问题、把尾后事件改挂最近版本。needs_review可提交且保留诊断。改稿须重新check，提交正文必须与最后核查一致。
"""

CORE_ADDENDUM = """
本次结论schema为migloop-verdict/2：target_file独立于repair；没有正式版本的动作写event_claims，不借最近agent@v；coverage只写有具体判断的reviewed，系统把认证清单补集列为not_investigated，不必复制长串未调查理由。结构全文见guide(topic=verdict)。
"""
