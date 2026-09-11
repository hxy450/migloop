# i04 输入入口与调用降噪

2026-09-11，模型仍为单个Luna medium，不重跑raw。沿用10文件/28核心，先跑会员页与Dice Index；源码、通用GUIDE、任务与池哈希冻结于独立i04目录。中途改动不进入本轮模型进程。

## 根据失败改什么

- 原文索引行和展开结果给转录所属agent入口；所属会话不认证被转述内容作者。
- file参与者给最后一次写调用发起前的input_scope，agent `view:inputs`将已成功返回的原生Read按文件归组，每次结果仍可展开。不把写入开始后才返回的Read当写前输入；不把此原生清单称为完整输入集。
- 关系视图的terms现在过滤请求/返回的真实正文，修正原来静默忽略过滤的问题。
- 原生只读工具与有限完整标准只读命令形状可折叠；数量、unfold和include_reads:true公开，records/search不受影响。不识别复杂脚本/替换/重定向，不推断写边，不用命令头判整个脚本。分类的前提是标准工具/命令语义，不认证运行时文件效应或自定义shell覆写。
- UI同样给所属agent、写前输入和只读展开按钮，共用Engine；输入/输出关系坐标区分读取观察时刻与写入时刻。
- GUIDE要求核对实际修改数量和回执，并区分“检查报告没有写”与“确认没检查”；否定后续成功回执必须用完整观察范围，不使用写前窗口。

回归79条通过，Ruff通过。索引结构明确为inquiry/index/2，报告仍inquiry/1；旧索引用对应冻结代码访问，或在新路径重建，不覆盖旧报告库。未切换legacy服务默认入口。

## 清理

已核实并删除i01三个没有任何模型运行记录（runs=0）的派生SQLite索引，合计约400MB；原始池、代码、清单和所有模型运行均保留，可从原始池重建。i02/i03/i03-high保留用于对照与复查。

## 尚未解决

机械校验不检查每个因果句子的真实性；自由正文中的伪造e-引用仍有校验空洞。原生读清单不包含全部shell/派发/消息输入。中间未知脚本不重放，也不根据目录猜作者。上述边界不能由“79测试通过”消除，需看实际Luna输出。

## 三跑结果：不接受

开发者按冻结核心和原文核验，非盲评。F10-01核心4/6（images/cta/indicator/repair-compile覆盖，price partial，mask wrong：未区分透明/深色且错误说4处统一补Palette）；F10-03核心2/5（button-style/comment-policy覆盖，label/logging partial，test-integration wrong：声称export后来撤回）；F10-09局部核心1/1。共3文件12核心中的7项，不是整个10文件分数。两个较复杂文件没有达标，不以Token下降作收益结论。

| 文件 | 秒数 | 总token | 帧完整呈现 | report_id | 状态 |
|---|---:|---:|---:|---|---|
| 会员页 | 402.08 | 1,704,437 | 72/74 | 85ed61ec3f174d23 | needs_revision |
| Dice Index | 236.58 | 1,762,730 | 88/88 | fb65e8319e044d66 | needs_revision |
| Codex Launch | 164.53 | 1,101,130 | 42/42 | fea3534b124c44ac | valid，仅机械 |

原文反证：Dice报告“之后整理撤回该导出”对应`agent-a228e9716d833cbf3.jsonl:L85`，原始diff中`export class Dice`是带空格的未变上下文，未被删除。会员页“回执明确报告本页4 sites”对应fixer L104原文3 sites；价格仍未使用Slice8 L24输入/L264输出。其query日志已实际列出Slice8输入清单，包括MemberCenterActivitiy.kt，但发现清单不等于展开并完成归因。Codex“没有修复后的新HAP”应限定当次修补，不能对完整观察窗口作无条件否定；报告把generated_dialog放到了agent scope上，节点主语仍有歧义。

真实Chrome载入Dice原稿通过：各finding节点/边与服务端图一致，显示原因、原文，手动探索不改调查轨迹；只读折叠前后数量一致，写前输入保留相同agent和时间。图6条可核边，不绘另外2条未核边，仍明确needs_revision。截图与审计`_migloop-scratch/inquiry-i04-dice-browser`，不是成功归因示范。
