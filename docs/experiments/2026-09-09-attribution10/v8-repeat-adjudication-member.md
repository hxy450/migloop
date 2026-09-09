# V8 Member rep2：两次都没有追到早期输入

第二稿固定六事实仍为 **4 supported、2 partial**：H5 既有透明例外漏掉，Slice8 在重写前已读正确 Kotlin 仍未调查。不能用“原始进入点未知”替代可完成的原始归因；也不能用第二稿覆盖第一稿。

实际 GPT-5.5 / medium / native，冻结源 `b540cb2`，2026-09-09 20:06:51 UTC 完成。同 `reference-v1`、同 Member 原始池、同题；没有修改运行、参考、源码或读取私有 holdout。完整原句、固定 facts、39 个原文 locator / 原事件 ID / SHA256 见 [JSON](v8-repeat-adjudication-member.json)。首稿裁决保留在 [v8-adjudication-member.md](v8-adjudication-member.md)。

## 固定事实

| 原事实 | rep2 | 依据 |
|---|---|---|
| S3.f1 三站点 AppLoad、PayAgreement、RenewRule | supported | 实际打开 L77/L80 扫描，逐名与位置正确。 |
| S3.f2 跳过已有 mask；AppLoad 透明，其余缺失项 Palette | supported | 打开 L103 完整脚本和输出，coverage 明称“实际执行”；脚本 write 在 report.append/输出之前，不能因为没有完整快照就拒认操作。未缺 mask 的预筛与 1 透明＋2 深色分类正确。 |
| S3.f3 3 是总数；H5 已透明且跳过 | partial | 三处不是三个深色控制器已说清；全文没有 H5。L74 既有 mask 扫描反而列为未调查。 |
| S4.f1 Slice8 写前已读 Kotlin 数字段逻辑，却统一 30vp | partial | 只读后来的 fixer 代码/Android 检查，明确说“原始缺陷进入点未追到生成期”。实际早期输入→错误整文件 Write 没调查。 |
| S4.f2 ForEach 中间态后再改两固定 Span | supported | L528 第一轮和 L592 尾后脚本都实际打开，30/16、helper 改写与阶段顺序正确。 |
| S4.f3 fixer 引入 private，builder 两 Edit 后编译成功 | supported | 看了 private 脚本、原生错误、两次 Edit、第二次实际构建回执。未把发现/修复者当错误来源，未把构建当视觉通过。 |

原始复核不是工具标签推断：

- fixer `agent-a68daf720e780b4c2.jsonl:L103/L104`：已写后报告 Member 3 sites；L106/L107 确实只读回 PayAgreement 一处。报告对另两处“最终是否保留”的未知合理，本裁决不要求由脚本成功证明最终设备状态。
- 同转录 L74/L75：Member 既有 `maskColor: Color.Transparent`；对应 H5 控制器在 Slice8 原生整文件 Write 中已存在，批量脚本跳过含 mask 的 controller。不能因没展开这段就把全体透明项当新增。
- Slice8 `agent-aslice8-pay-80bbb1f44b77da0f.jsonl:L21/L24`：07-24 15:33:49 发起、15:33:51 返回 Kotlin，276–282 行只把数字段放大 30。L264/L265 在 16:04:37 成功 Write，非滚动价格仍整串单 Text 30vp。这条可用证据没有消失。
- fixer L592/L593：07-26 21:30:17 写固定双 Span 和 private helpers；同 ID 输出 `ok` 后还读回代码。builder `agent-af0e3d2ae54dbf769.jsonl:L23/L24、L32–37` 支持新编译错与两次修复。

S3 保留真实执行、最终持久状态和设备真值三层区别。S4 原始进入链缺失，不因更保守而得分。

## 实际路线：入口送达，但没跟进

42 次调用：guide 2、sessions 1、action 24、diff 5、file 1、search 8、check 1。**0 agent、0 blame**，没有打开 v7 或 Slice8 的任何原文。

仅有的 file v16 查询（第 14 次，transcript L78）已给出真实作者 `agent-aslice8-pay-80bbb1f44b77da0f`、v7 原始 Write 引用 `#80bbb1f44b77da0f:13670@L264`。第 15 次 maskColor search（L92）再返回 v7 的透明行和精确导航 receipt。没有跟进；与首稿收到 blame recovery 却不跟进不同，这次连 recovery 都没请求。

24 次 action 都使用 ref，但不是全部成功：第 10 次将 builder 的序号/行错误地配上 fixer tag，返回 `isError=true`、`missing；不得仅按 #n 猜测`（L60）；下一次改成正确 builder tag 成功。metrics 的 rejected_calls=0 没把这类 MCP 错误计进去，不能据此说“零失败”。最终报告没有保留这个错引，39 个不同原文引用均定位到真实事件。

8 次 search 都是文件已知内容或指定 fixer/builder 的效应范围；无 until_ts，也无 seq-only until。未发现时间筛选错误被用来伪造早期输入，本次根本没有进行生成前输入核查。

## 完整标注仍有问题

第一，S3 又出现 `repair.before=v9 / after=v16`，而 v16 的真实操作是 builder 去掉 priceSuffix 的 private，不是 mask 插入。模型同时承认 v16 内容未知，却给 mask 绑定这个宽范围的修复落点；它不能证明 mask 效应在 v16 成立。首稿已没有这一伪精确 mask repair 对，第二稿退回了宽范围替代。

第二，尾后 #15731 仍写在 fixer@v40 节点的 reason/evidence 下。动作原文头（L137）明确“喂养槽41、已记录40个效应、无可导航版本”。这次角色是“无法确认”，不是首稿的红色进入点，也没有从 v40 造写边；正文承认尾后边界。但 UI/汇总仍不得把该内容当成 v40 窗口内实际发生，节点可定位不改变事件时序。

第三，compile.before=v14 被明确限定为“上一正式版本的账本边界，不能声称它已含错误”。这个披露应保留：v14 真实只添 banner 常量，private 在另一个后续脚本；不能把 build1 原文当成 v14 快照。after=v16 的两次实际修复有依据，与 S3 无对应效应的宽范围锚点应分开评估。

另外同一 S3 fixer@v5 同时标“正常”和“无法确认”，分别讲操作与验证。check 原样保留并提示角色冲突，没有替模型选一个状态。没有红节点或 basis；这不是通过删 basis 自动证明语义正确，而是 v1 下允许的非红声明。

唯一 check（第 42 次，L214）为 **needs_review，0 errors＋1 warning**，最终 matched。warning 是上述角色冲突，不是 clear。既有边界检查只扫描红节点 basis.actual_evidence，不扫描非红普通 evidence；因此这次没有尾后/后置 basis 警告是设计范围，并不认证 v40 绑定。

coverage 38/38＝7 正式版本＋31 候选，15 explained、23 out_of_scope、0 not_repair。题外 v10/v13/v14、图片等不冒称非修复；L501 价格 finding 正确采用。L615 未调查允许，但它不能补足遗漏的核心早期输入。38/38 不表示语义完整。

## 两次并列，不择优替换

| 项目 | V8 rep1 | V8 rep2 |
|---|---|---|
| 固定事实 | 4 supported / 2 partial | 4 supported / 2 partial |
| H5 既有例外 | 漏 | 漏 |
| Slice8 早期 Kotlin→错误 Write | 未调查，仍标红 Slice8 | 未调查，明确未知、不造红 |
| recovery | 返回一次，未跟进 | 未调用 |
| 尾后动作 | v40 红节点 | v40 无法确认节点 |
| S3 精确 repair 对 | 未编造 | 重加 v9→v16 |
| Check | 0 errors / 4 warnings | 0 errors / 1 warning |
| Input（已含 cached） | 762,351 | 846,003 |
| 其中 cached | 672,768 | 689,664 |
| Output（已含 reasoning） | 18,782 | 12,859 |
| Input + Output | 781,133 | 858,862 |
| 模型运行秒 | 525.383 | 287.656 |
| 端到端秒 | 539.277 | 301.400 |

两次 total 均值 **819,997.5**，比 V7 Member 两次均值 1,349,627 少 **39.2%**；模型运行均值 406.519 秒，比 V7 少 5.7%。cached 与 reasoning 各已包含，不重复相加。两样本仍不足以证明稳定因果收益，且多项接口同时变化。

两次 V8 都重复同样的早期输入/H5 缺项；V7 两稿曾在 coverage 提到 H5。少了首稿某个红色错误，不等于补全原始归因；也不能为了成本好看忽略重现的伪 repair 范围。当前联合验收仍未证明。
