# 新跨运行候选：完整资料登记与显式源合同

2026-09-10。此候选与正在跑旧十文件的冻结tools-v4分开；没有修改v4包、旧原始组或任何历史答案。修改来自新数据目录/字段元数据预检和合成反例，尚未阅读新队列归因参考或模型报告。

## 实际发现，而非泛化结论

冻结源`source-freeze-1/source-manifest.json` SHA256：`92d42b2d7b7dcf6a5cbebb4498f2036ca0130be56a65f218e57d55905c9d0e89`。dynamic1完整169文件，arch11完整385文件。

旧v4实际注册验证失败：dynamic1 **1/78 JSONL**，arch11 **193/193 JSONL**。旧验证记录保留。dynamic的77子JSONL不是77个agent：70份原生agent转录和7份workflow journal，后者不能制造agent身份。其余91个文件包含70份agent元数据、7份workflow JSON、10份保存工具输出txt和4份脚本js；这构成原始组可读而旧工具不能检索的真实资料差，不以“sidecar”名义忽略。

## 统一规则

`cc_sources.all_source_paths(root)`登记显式root JSONL及对应root-stem目录内全部普通附件，递归、排序、拒绝链接/特殊文件和actor身份碰撞。脚本预扫与actor收集复用同一次发现的原生actor集合，非actor附件独立存入`Ledger.auxiliary_sources`。共享service的缓存签名也看所有附件，新增、追加、删除均使账本失效。

每个源有显式`source_metadata={logical_name,timestamp_policy}`：逻辑名由选定root及其相对目录构造，不从主机绝对路径猜归属；actor转录保留记录时间，辅助材料用unknown。附件中的JSON `timestamp`、mtime、所处目录和提到的agentId都不认证到达时间、输入关系或作者。原始索引不把附件引用的tool_use或patch_apply_end当实际执行事件。

原文访问共享`SourceSpec`。20位basename旧引用在唯一匹配时仍原样解析；显式逻辑名产生40位qualified源键，解决同名journal但不合并不同来源。20/40分别核原始行内容hash。原型曾试图从路径里的subagents推导命名空间，独立反例发现主机父目录也可能同名；该未冻结原型已替换为显式合同，不曾用于正式模型实验。

所有源合同进入账本身份、原始解析缓存与latest截止缓存；不能只改search而让diff/changes/legacy展开仍用另一套原文规则。附件可全池或词法检索，未知时间单列，需显式include_undated展开，不能升级成agent输入。无法解码的二进制/损坏字节保留来源和gap，不声明正文可读。

UI将可定位但undated的证据提供为“全池独立查阅”，保留原时限并注明不认证节点输入；不修改模型轨迹、原e.scope、节点判定或历史边。正常证据沿原范围展开。

## 验证与冻结门

第一轮嵌套源/缓存反例5项先失败；地址原型6项失败、2项通过。之后包括aux原文、明确时间合同、缓存、changes及旧引用消费者的联合回归284 passed、6平台symlink skip。一个中间版本全套2593 passed、9 skipped、1合成ZIP重复项警告，208.55秒；这个数字不冒充最终显式合同版本的全套结果，最终复跑另记。

新候选先单独冻结runtime及原v4哈希绑定的helpers，再验证**169/385完整文件集合**，JSONL子数另列；正确数量但错误源集合不能放行。UTF-8 decode gap与注册分开，注册完整不等于原文已交付或模型已读。门通过后才构建、交叉复核并封存13个新文件参考/core，再运行两组Luna medium。该队列仍只是已披露曝光的跨运行检验，不称未见业务泛化。

旧v4继续按原条件跑完整20次，所有失败保留。此过程中有并行源码测试、源冻结和哈希工作；v4耗时是实际测量，不把差异宣称为独立隔离出的性能因果效应。最终成本报告应披露此背景负载。

最终显式合同版本全套复跑：**2625 passed、9 skipped、1合成ZIP重复项警告，209.94秒**。独立SourceSpec/调用者合同联合复核351 passed、6平台symlink skip；新增测试若晚于全套collection单独计，不重复相加。没有据测试数量宣布因果正确、真实全附件注册已通过或模型提升。

候选源码提交`834505f`；冻结目录`EVAL/generalization-20260910/candidate-source-v1`，manifest SHA256 `60640cdb5075538a783cc5c93e9ab881f5d4a4b21b6d83672ef7e7200311e1bd`，code digest `0cf294977c1c622fe0503123f369e4956a328aec83954303bad3c4bdb4e06455`。包括保留的service/deveco用户工作区字节，以code manifest而非仅Git提交为准。独立SourceSpec HTTP/MCP/模板JS及旧回执兼容联合67项通过，另见[sourcespec-transport-audit.md](sourcespec-transport-audit.md)。真实源注册与MCP门的最终产物在source-freeze-1单独保存，不复用旧v4检查结果。
