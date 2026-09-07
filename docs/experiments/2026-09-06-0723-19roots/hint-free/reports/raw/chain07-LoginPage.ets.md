```
文件: entry/src/main/ets/pages/LoginPage.ets  修复方: visual-fixer「fixer-r1」(agent-a68daf720e780b4c2, spawnDepth=1, toolUseId toolu_01APi9vUJuvdDSBK2JqMebM4, 属修复轮会话 ff019d8a)  修改时间: 2026-07-26T21:17:19.756Z(主改)、21:22:04.214Z(同一 agent 的第二处)
修复改了什么: 在页面 NavDestination 的 .hideTitleBar(true) 之后补挂 .onBackPressed(() => { this.navPathStack.pop(); return true })，让系统 BACK 键复用左上角返回箭头的同一条出栈逻辑；同一 agent 稍后又把标题栏返回图标从写死的 24x24 改成资源固有比例 12x19vp。
修复的依据: round-1 真机实测缺陷单 CRASH_PLoginActivity_back_failed_LoginActivity_to_MineFragment（P1、is_migration_bug=true、nav_mismatch_type=missing_handler，anchor 写明「Android LoginActivity 为独立 Activity，系统返回键默认 finish() 回上一页」），由验证 agent vv-t1-A02 在 16:59:31 生成；fixer 落刀前还比对了 ManageRenewPage.ets:265-269 已有的同款写法。注意 fixer 未采纳缺陷单建议 #2（「不实现 onBackPress 或 return false 交还系统」），改用了与兄弟页一致的 pop()+return true。
被改代码的来源: 纯新增。原文件由生成轮 conv-login(a2h-activity-converter, opus) 于 2026-07-24T02:35:44.418Z 一次性 Write 出来，全文 0 处 onBackPressed，NavDestination 尾部只有 .hideTitleBar(true) + .onReady(...)。前一版没写的原因是它的输入里没有任何信号：Android LoginActivity.kt 本身未重写 onBackPressed（源码驱动的转换器无可转之物），team-lead 下发的任务参数里没有返回键约束，它读过的 _common.md、android-to-harmony、ui-migration 三份规范和两份参考页(ChoiceTemplatePage/GuidePage)全部 0 次出现 onBackPress。（那段 .onReady 后来被别的 agent 删掉了，删除者无法确认。）
生成时为什么没做好: 断在转换器的「规则供给」环节——`.onBackPressed → Activity 默认 finish()` 这条约定从未写进 a2h-activity-converter 的 _common.md/参考文档或页面任务参数，只靠各 conv 子 agent 随机读到的兄弟页样例口口相传，conv-login 恰好抽到两个没有标题栏返回箭头的参考页，于是漏掉。
是否必要: 必要，真机双击 BACK 页面纹丝不动、只能靠左上角箭头退出，是可复现的 P1 导航退化。
证据(每条带位置):
  1. 修复本体：9b3105a2 同级目录 ff019d8a-.../subagents/agent-a68daf720e780b4c2.jsonl:449（uuid a1844d59-c03e-420c-8193-7d0121b0d56d, 2026-07-26T21:17:19.756Z），Edit 的 new_string 即 .onBackPressed 块，注释自述「round-1 实测：本页此前未挂 onBackPressed」。
  2. 真机证据：agent-a96b301d9764dca23.jsonl:314(16:41:50.576Z) 与 :317(16:42:19.081Z)——两次 `uinput -K -d 2` 后 dumpLayout 仍为「手机号登录/获取验证码/我已阅读并同意」，紧接着点 (90,200) 返回箭头一次即出现「点击登录/账号管理」(MineFragment)。
  3. 缺陷单生成：agent-a96b301d9764dca23.jsonl:414(16:59:31.304Z) render_finding_skeleton.py --id CRASH_PLoginActivity_back_failed... --severity P1 --suggested-files LoginPage.ets,HomePage.ets。
  4. 原始写者：agent-aconv-login-251236e9c3d44116.jsonl:55(2026-07-24T02:35:44.418Z) Write LoginPage.ets，全文 onBackPressed 计数 0；文件尾为 .hideTitleBar(true) + .onReady(...)。
  5. 输入缺规则：同文件 :1 的 team-lead 任务参数（只有 D-008/资源映射/沉浸式 Layer 3 三条约束）；:21 LoginActivity.kt、:30 _common.md、:34 android-to-harmony、:40 ChoiceTemplatePage、:46 ui-migration、:50 GuidePage 六份读入内容 onBackPress 出现次数均为 0。
  6. 兄弟页对照：agent-aconv-managerenew-b9f5799b407aa4aa.jsonl:20 的 tool_result 里，被引用的参考页已带 `.onBackPressed(...)// Android BaseBusinessActivity 默认返回（finish）→ 出栈`，同一句注释被原样复制进 ManageRenewPage(fixer 于 :445 grep 到 265-269 行)。
  7. 第二处改动：agent-a68daf720e780b4c2.jsonl:506(21:22:04.214Z) 的 python 批处理，末段单独把 LoginPage 的 `.width(24)/.height(24)` 换成 `.width(12)/.height(19)`（其余 13 个文件走 dp_24 分支），:507 回显 `ok entry/src/main/ets/pages/LoginPage.ets`。
  8. 未复验：fixer 会话到 :615(21:41) 只在写缺陷单归档，无 hvigor/编译/回归；主会话 ff019d8a-....jsonl:1761(21:48:28.597Z) 改 report.md 时「下一步 1. 编译验证 fixer 的…」仍挂着，会话在 21:48:57 结束。
无法确认的部分: (a) conv-login 原写的 .onReady(...) 块被谁、在哪一步删掉——生成轮有 aslice2-auth / agroup2-closer / 多个 batch-closer 都编辑过本文件，未逐一比对；(b) 本次 onBackPressed 修复后是否真的编译通过、BACK 是否真的回到 MineFragment，转录内没有任何复验记录；(c) 生成轮的 closer/审计环节是否曾把 LoginPage 的返回键列入检查项，未查证。
置信: 高——修改点、依据缺陷单、真机复现证据、原始写者与其六份输入的缺规则事实都能直接落到具体行号，唯一未闭环的是修复后的复验(见上)。
```