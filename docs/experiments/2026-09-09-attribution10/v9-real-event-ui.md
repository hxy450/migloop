# V9 真实输出的事件与调查路径 UI 验证

冻结源码及页面均为 `0be4164`。使用真实 GPT-5.5 输出 `holdout-v3-eval-0be4164/h3-p1/runs/tools/rep1`；该题已在冻结前部分暴露，**只属于展示验收附录，不属于严格盲评子集**。

原始运行最终提交通过来源与双哈希核验，文档为 `migloop-verdict/2`。页面载入完整 run，不是把模型 YAML 自述当调用轨迹。

- 66 次真实调用，18 条版本访问记录（14 次成功、4 次未打开）；12 个独立已显示版本节点。
- 页面与载荷的 13 条导航转换逐条一致；2 条账本读写边一致。其余导航不冒充数据流边。
- YAML 声明的 4 个事件，其 ID、原文坐标、角色、原因与事件绑定元数据逐项等于页面内容。4 个“原文”按钮均打开对应原始动作；展开后完整 input/output 与相同 HTTP action 结果一致。
- 展开原文、核验记录和事件理由前后，根节点、模型步骤、调查路径、证据图均不变。真实轨迹快照 SHA-256：`75a15d922170cef0586fa0d8c95946281fe58ee7734fcbbf11619db030d2fd8a`。
- 4 个事件均为非红角色，未声明事件 basis；如实记录，没有把缺失字段算作已测试的红事件 basis。红事件/上下文不染红的边界另由合成浏览器回归覆盖。
- 模型的两个 check 共 6 项检查提示均可见；最后一次 check 为第 66 步。无 JavaScript 异常；初始图形无重叠、无越界。

截图：[整图](screenshots/v9-h3-p1-rep1-geometry.png)、[事件原文与核验面板](screenshots/v9-h3-p1-rep1-events-basis.png)。可复跑检查器为 `tests/browser/probe_basis_smoke.cjs`。

检查器首次错误地要求原文抽屉包含 canonical reference 字符串；实际抽屉展示的是结构化动作的 input/output，坐标在事件条目另列。修正测试为核对原始动作地址及完整正文后通过；这不是生产页面缺陷，也没有重写模型产物。

这份验证证明上述真实输出能被忠实呈现，不证明四条事件理由的归因语义正确，也不证明模型阅读或理解了人后来展开的完整原文。

## Member 的红事件 basis 与旧版回归

同一冻结 V9 源的 Member rep1 也完成实际载入：2 个事件的模型原文、理由、basis、绑定及完整原始 input/output 均逐条通过；最后 check 为第 44 步，零提示。页面未声明普通节点 basis，所以该字段如实为 missing；事件 basis 实际验了 2 个，不能混为一项。根、5 个图节点、4 次版本访问及原始步骤快照均不变（SHA-256 `c4278450a8514710caefd93a4f18bbe04d67abb1dd885be394c90a4fc8474bfc`），无 JS 异常。[截图](screenshots/v9-member-rep1-events-basis.png)。

扩展检查器另外回放 V8 Member rep1／冻结查看器 `0a79ade`：旧版节点 basis、2 次 check 的9项提示仍通过，声明事件为0，不虚构补充；所有历史轨迹不变。[截图](screenshots/v8-member-replay-v2-smoke-helper.png)。
