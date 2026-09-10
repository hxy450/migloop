# tools-v1：Codex 两题机械可达性对账

状态：**已完成冻结 tools-v1 实测；两条真正的 native patch 均可达，但存在额外 outer-call confirmed 行和过强作者绑定；快照差异未结构化。**

预登记阶段按父端要求避免与正在计时的 20 runs 竞争 CPU，只读参考与指定原始行。队列于 2026-09-10T13:29:02Z 全部停止后获准实测。成功主查询时间为 13:45:32.708947Z–13:46:00.610526Z，27.905 秒；补充原文展开/Action proof 查询为 13:47:52.103980Z–13:47:56.515834Z。没有运行模型或执行任何历史命令；没有向调查员传参考内容。此前 13:44:35.806774Z 的约 3.1 秒尝试只完成 hash/建账后因 stdout 编码中断；随后按冻结设置补 `-X utf8` 重跑。

## 固定范围与来源

- 冻结工具：`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v1/code/src/migloop`，父端冻结提交 `d02c866`；实际查询必须隔离导入此目录，不能落到工作树 `src`。
- 环境：从 `tools-v1/settings/F10-09.json` 的 `mcp_servers.migloop.env` 原样加载；F10-10 同一 Codex 池/anchor/roots。查询进程使用冻结设置指定的 Python，并关闭字节码写入。
- 原题：`baseline-v1/tasks/F10-09.md`、`F10-10.md`。修改窗口均为 `(2026-08-16T23:49:46.899Z, 2026-08-22T15:24:43.116Z]`；上游证据查询不继承该修复起点。
- 池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/codex-c1/pool`。只有两个 root rollout，不能补出 child 原始输入或写入。
- A：`rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl`，登记 SHA256 `9dc4529045f70a6d493fe2ae05d215fac4990e6dcbafc59dce20d69ac2de8679`。
- B：`rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl`，登记 SHA256 `a97f9363d03178ef394c593b9274b1b954574b093172e5cfb072712ce1540460`。

上列两个 source hash 已在实测时重新核对一致。冻结 code-manifest 的 62 个文件全部 hash 一致，content_digest=`ce685b2ded0a8cccdfb63ff18a2353a1b6eee0b31b8e47409f38ec48fcba1ca4`。显式检查 service/investigation/temporal_state/raw_events/change_inventory 均从 `tools-v1/code/src/migloop` 导入，不是当前 repo v2。账本 ID=`atoms-2026-09-10-temporal1:2:31c71be6b37fa4bbd585cbd4`，2 个注册 agent、2 个 source、4269 个 Action；成功主进程建账约 2.157 秒。生成边界 A:7687 是 execute 完成消息；截止 B:7916 是最后 raw record，不是最后产品修改。

原题语义为“生成结束之后”；冻结 API 的 since/at 实际均为 inclusive。两条 patch 都严格晚于边界，此差异不影响本对账结论。下面保留原始 UTC 精度；工具输出会规范化为六位小数。

## 真实修改与待对账条目

完整产品路径前缀为 `/Users/ventiu/Desktop/HUAWEI/AIPPT_830_test/`。A/B 行号是物理 JSONL 行，不是源代码行。

| 原题 / 原始定位 / UTC | 原始事实 | 查询对账要求 | 实测状态 |
|---|---|---|---|
| F10-09；A:8067；2026-08-17T03:11:06.817Z | 独立 `patch_apply_end`，`success:true`，精确目标 `entry/src/main/ets/pages/LaunchAgreementDialog.ets`；`HitTestMode.Block → Default`，隐藏分支仍为 None | 应在 changes/events 可达；确认操作不能认证来源 agent 是作者 | changes/events/原始字段展开均可达，native 行作者 unknown |
| F10-10；B:4944；2026-08-21T11:15:04.181Z | 独立 `patch_apply_end`，`success:true`，精确目标 `build-profile.json5`；product 的 name=default 后增加 `signingConfig: default` | 同上；不能扩大成证书创建、口令更新、SDK 变更或 API signer 修复 | changes/events/原始字段展开均可达，native 行作者 unknown |
| F10-10；A:7970；2026-08-17T01:30:34.519Z → B:4930；2026-08-21T11:14:42.786Z | 两次配置正文读回不同：后者多了已有 default signingConfigs，compatibleSdkVersion 从 6.0.2(22) 变为 6.0.1(21)；两者 product 均尚无 signingConfig 引用 | 只能算观察区间，不认证唯一作者或写入时刻 | events/原始字段均完整可达；changes 没有 observed_change，diff 没有这段快照差异 |
| F10-09；B:6090；2026-08-21T16:29:54.146Z | 读取到 Round 0 fixer 报告声称改过 LaunchAgreementDialog；此行不是产品 patch | 应留报告/相关原文导航；不得仅凭 FILES_MODIFIED 升级 confirmed_change | events 以 B:6089→6090 返回事件可达，未被列为该文件 confirmed_change |

A:8067 的原生 call_id 是 `exec-4ef57557-1919-4ec6-b81e-4b4d9d8c112a`，行 SHA256 `fde44a196809789bce24817c825227a5809b4f3dd08ae7c53f6fd7752fcc7b73`；B:4944 是 `exec-9c2b0363-9806-4d9a-8733-06f2e3379843`，行 SHA256 `326517f6f7207b954fb0f515489aaee0a2e8a458ef06af3eb297208c129f6472`。本次已重读两条原生 success/changes/unified_diff；行 hash 仍为既有 inventory 登记值。

相邻 outer call 分别是 A:8066 `call_sOYpciVhfgk1glebywbIbHAY`（03:11:06.675Z）和 B:4943 `call_bLvRxsabKt5jwrDAGfcDP0LK`（11:15:04.158Z）。其结果 A:8068（03:11:06.825Z）、B:4945（11:15:04.202Z）与各自 outer ID 相同，但不是独立 event 的 exec ID。不能仅按相邻位置/空结果把 inner 写入绑定给 outer actor。

## 原因、反证与验证范围的导航对照

这些不是额外必答单元，也不是已确认修改；仅核对工具没有把不同证据类型混淆。

| 原始定位 / UTC | 可支持的事实与限制 |
|---|---|
| A:5527 / 2026-08-16T20:39:49.665Z；A:5640 / 20:45:39.696Z | 生成期间主线程读过 F001 spec 和 source-notes；不等于 child 全部输入可还原。 |
| A:5717 / 2026-08-16T20:52:57.556Z | `/root/close_batch_02` 报告创建 Launch，`BUILD: NOT_RUN`；报告不代替创建 patch，也不能泛化成全阶段无任何编译。 |
| A:7997 / 2026-08-17T03:09:20.059Z | 用户报告同意无反应，不是本次审计重现。 |
| A:8027 / 2026-08-17T03:10:07.647Z；A:8037 / 03:10:28.882Z | 原始源码读回有子按钮 onAccept 和父 SplashPage 回调接线，反驳“已经证实没接回调”。 |
| A:8052 / 2026-08-17T03:10:48.522Z | `call_pcfEmHYX0diVq2Wp6lSznwzl` 返回完整 Block 枚举和阻断子节点命中语义；接受已登记 amendment，不以较早 A:8048 的截取边界为证据上限。 |
| A:8101 / 2026-08-17T03:11:45.666Z；A:8110 / 03:12:02.536Z；A:8115 / 03:12:10.312Z | 当次 validate 配置缺失；读回 Default；报告现有 HAP 仍修前版本。源码改成功与修后设备点击通过不同。 |
| A:4441 / 2026-08-16T19:39:04.080Z | stage-1-close 报告“移除失效的空签名配置引用”，是确实存在的历史报告；不是本池已证实的原生删除 patch，也不能说该报告已被证明虚假。 |
| B:4930 / 2026-08-21T11:14:42.786Z；B:4934 / 11:14:48.679Z | 配置读回确认已有 default 签名配置而 product 无引用；D-019 允许现有调试签名。报告仅保留结构，不复刊凭据。 |
| B:4966 / 2026-08-21T11:16:05.982Z | child 的 signed-hap/SignHap 成功报告，不当 root-visible 编译器 stdout。 |
| B:7694 / 2026-08-21T20:37:07.829Z | 后期真实 build/install 输出，不自动证明 A:8067 补丁对应四类按钮或业务登录验证成功。 |

冻结核心只有 `F10-09/hit-test`、`F10-10/signing-reference`。上述辅助项遗漏不自动清零；没有 child 原始正文时不得强迫唯一作者归因。A7970→B4930 的新增观察差异按既有 amendment 接受，但不事后增加必答单元。

## 机械查询方法

1. 核对 frozen manifest 中模块与 source hash；从冻结设置取 env，`-I -B` 启动单个 Python 进程，仅导入 `tools-v1/code/src`。记录审计开始/结束 UTC，与实验计时分开。
2. 用 frozen `service.session_ledger(anchor)` 只建一次账；记录 roots、source 数、agent/action 数、实际导入路径。不序列化整份大账本。
3. 对两个精确产品路径完整分页 `investigation.changes` 至 `next_offset=null`，记录 total/status/id/raw refs。逐一与 A:8067、B:4944 及观察差异核对；若同 source/line/path 重复，记录去重问题。
4. 用同一文件窗口分页 `events`。确认独立原生 patch/result 与 outer call 各自可达；再用 `record/expand` 精确展开已知 raw ref 的 `/payload/changes`，不把词法相关 `events` 行当效果证明。
5. 查询 `diff` 和仅观察时点的 `blame`：生成边界、两条 patch 各自前 1 ms/记录时刻/后 1 ms、最终截止。核对返回前无 future patch；独立原生效果后不得继续把旧快照报 `known:true`；后续可靠全文最多恢复观察内容而非未知作者。
6. 单独查 A7970→B4930：如果没有可靠全文结构而仅 raw 输出，应报告“snapshot 差异人工可核、changes 未结构化”，不能硬算漏掉确认写入。若 diff 是其他分支/路径的净变化，不能据文件短名误配本题。
7. 结论分四栏：changes 已有；仅 events/raw 可达；仅 snapshot 差异；仅报告声称。另列假 confirmed / 旧状态误 known 的实际复现或“本范围未发现”，不能以代码意图代替执行结果。

## 实际分页与原文展开

两题均使用精确产品路径、原题 since/at、limit=200 查询，所有主/附属页的 next_offset 都为 null，无第一页截断。

| 输出 | F10-09 | F10-10 |
|---|---:|---:|
| changes.total / confirmed_change | 2 / 2 | 2 / 2 |
| changes.observed_change / candidate_effect | 0 / 0 | 0 / 0 |
| events.total / unknown_records / undated | 9 / 3 / 0 | 11 / 0 / 0 |
| 独立 codex_patch 事件 | 1 | 1 |
| diff.total / known | 1 / false | 1 / false |
| changes/events/diff source gaps | 0 | 0 |

真正 patch 的 changes ID 分别为 `native-change:9be5c4f466ae3be0290b53ed`、`native-change:4fb559fe655216b8a15c8a86`；对应 native event ID 为 `native:a6388d94ade69bd2a960af48`、`native:e5596068372d0900099370f9`。两者都有 `raw_only:true,agent:null,author_status:unknown,use_ts:null,changed_time_unknown:true`，观察时间分别精确到 A8067/B4944；没有漏到只可 events 访问的情况。

file scope 下 `expand(ref,pointer=/payload/changes)` 均成功且无 withheld，完整交付 405 / 259 字符、next_offset=null；field SHA256 分别 `8d8576bc21f9907f3a582e16afdd27ac7ec25b5492b0c21a3ddd5820195b510a` / `ee27cfcfec02f93b980b305de9403959bdb7179a9592e1f9208b7cb65f6ab7cd`。展开后精确目标和两段 diff 均与原始 inventory 一致。

A7970 的 raw ref 为 `raw:cc96d29f0c27def672ec:L7970:7e01b8c512cef4c4f361`，B4930 为 `raw:4098e845544bb2c28eb1:L4930:0e6f207b1bb101a63c4c`。二者的 `/payload/output/1/text` 在 file scope 均能完整展开，交付 8677 / 1507 字符、next_offset=null。只检查并记录签名配置结构与兼容 SDK 值，不复刊凭据；其 field SHA256 为 `be0dc448f8687f0b7c3172f3e53794291924979ba3e748d5d5553b7d71d848bc` / `1b4530e71035ea1ef1663b52cfa15406b9aa70d147d024ca8783283c7708ebad`。

未生成 observed_change 的机械原因：A7970 对应 Action 2369 为 exec/other，目标 FileRefs 为空；B4930 对应 Action 4005 只有 supported_shell/read、snapshot=partial、full=false、content=null。冻结算法要求两侧可靠完整 Read，不把任意外层 exec 返回强装为全文状态。故这段材料不是不可访问，而是需要调查员对原始返回做结构比较；不能因为 changes 的两条确认行就宣称全文件只发生一项实质变化。

只留 events/相关导航的实例：A8026→8027 的目标源码读取；A8109→8110 的 Default 读回；B6089→6090 的 Round 0 修复报告。build-profile 的快照调用为 A7969→7970、B4929→4930。它们不是新的确认写入。冻结 `unclassified_related` 只有一个 events 查询指针和 note，没有 v2 的余项分类/计数，gaps=0 不证明 unclassified=0。

## 额外 confirmed 与作者绑定风险

changes 的第二条分别是 outer call `...:call_sOYpciVhfgk1glebywbIbHAY` 和 `...:call_bLvRxsabKt5jwrDAGfcDP0LK`；均返回 confirmed_change、agent=`__main__:01a009fe` / `__main__:01a021e5`，证据只有 A8066/A8068 或 B4943/B4945。其 Action 2400 / 4010 被解析为 `native_tool, execution=confirmed, rule=tool:edit`。

这比独立原生事件可证的内容更强：它确认了一条有作者的额外操作，但 outer 空结果与不同 exec ID 的 inner event 尚未证明一一配对。真实 patch 本身不是假的；**不能把这两种视图当成两次独立实写，也不能用额外 confirmed 行认证 outer 是唯一实际写者**。因此本范围发现了过强 confirmed/作者归属风险，不是“原生写入不可达”。同 source/line/path 的去重规则无法消除这组不同物理行的候选联系。

同一风险延续到 diff：F10-09 返回 `#01a009fe-68e3-7f42-b76b-5e863c555976:2400@L8066`，时间为 outer 返回 2026-08-17T03:11:06.825Z，diff_chars=173；F10-10 返回 `#01a021e5-c150-7b12-a610-d40c07816b98:4010@L4943`，时间为 2026-08-21T11:15:04.202Z，diff_chars=141。二者均 basis=native、agent 为 root，即使顶层 known=false。局部差异内容可核不等于精确写入时刻、作者和内容传递已被证明；不应把该 agent 字段当评分真值。

## 补丁前后 1 毫秒与状态

| 文件 | 查询 UTC | known / blame 行 | native barrier |
|---|---|---|---|
| Launch | 2026-08-16T23:49:46.899Z | false / 0 | 无 |
| Launch | 2026-08-17T03:11:06.816Z | false / 0 | 无 |
| Launch | 2026-08-17T03:11:06.817Z、.818Z | false / 0 | A8067，作者 unknown |
| Launch | 2026-08-17T03:12:02.536Z；2026-08-22T15:24:43.116Z | false / 0 | A8067，作者 unknown |
| build-profile | 2026-08-16T23:49:46.899Z | false / 0 | 无 |
| build-profile | 2026-08-21T11:15:04.180Z | false / 0 | 无 |
| build-profile | 2026-08-21T11:15:04.181Z、.182Z | false / 0 | B4944，作者 unknown |
| build-profile | 2026-08-21T11:16:05.982Z；2026-08-22T15:24:43.116Z | false / 0 | B4944，作者 unknown |

本真实池没有发现旧状态错误地继续 known=true，也没有在原生观察时间前泄漏 native barrier。必须保留验证范围：这些文件修前就未被重建为 known=true，因此本次不是一次真实池里的 known→unknown 转换测试；只证实截止与 unknown 作者投影正确，不证明所有状态重放场景完备。

## 当前结论

两条真正独立原生写入均在 changes/events/expand 可达；没有本题真实 native patch 只藏在 events 的漏项。签名配置的额外变化仅是 raw 可核的快照差异，未进入 changes/diff。Launch fixer 后续声称另改与 stage-1-close 声称删除仍是报告事实，不能升级实写。发现 outer-call 重复确认/过强作者绑定风险；未发现这 12 个截止检查中的 stale-known 或未来 native barrier 泄漏。未保存整份账本，未改工具、runner、冻结快照或评分合同。
