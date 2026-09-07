```
文件: entry/src/main/ets/components/WorksComponent.ets
修复方: visual-fixer / "fixer-r1"(agentId a68daf720e780b4c2，由主会话 ff019d8a 于 ff019d8a-…jsonl:1712 2026-07-26T20:33:31Z 派发 toolu_01APi9vUJuvdDSBK2JqMebM4)
修改时间: 2026-07-26T20:54:51.158Z（主改动）+ 2026-07-26T21:22:04.214Z（附带的图标尺寸批改）

修复改了什么: 主改动把 onWorksItemClick 里的 `pushPathByName('PPTFilePage', params)` 改成 `'PptFilePage'`，并订正上方写错的注释、补一行防复发说明（未动 pageMap）；同一 agent 稍后在一次 13 文件的批量脚本里顺带把本文件 :686 标题栏返回箭头 `dp_24 × dp_24` 改成 `12 × 19`。

修复的依据: 工单 `spec/fix/round-1/feat/PPTFilePage_01_works_item_route_name_mismatch.md`（P0，kind=IMPL_MISSING）。工单证据链是三点静态对照：SplashPage.ets:381 pageMap 注册名为 `'PptFilePage'`、WorksComponent.ets:586 推的是 `'PPTFilePage'`、同一目标页的另一个消费方 TemplatePreviewPage.ets:255 用的是正确名 —— 故判为单点笔误而非命名约定问题；Android 锚点 `WorksFragment.kt:265 PPTFilePage.previewPPTFile(activity, model, true)` 证明该入口在安卓侧是活的。fixer 改完还跑了全仓 `pushPathByName/replacePathByName/…` 字面量集合 与 pageMap 20 条 `name === '...'` 的差集，结果为空。

被改代码的来源: conv-worksfrag（agentType a2h-activity-converter，生成轮 9b3105a2 的 in_process_teammate）在 2026-07-24T06:30:51Z 首次 Write 本文件时写下。它的依据是自己在 06:25:38 跑的一条「查路由注册名」grep —— 但那条命令只匹配 `pushPathByName('…')` 调用点、外加 `grep -rln "pageMap|…" pages/*.ets | head`，返回的是被 `head` 截断到第 10 个文件的字母序清单（AccountInfo…RefundProgress），**SplashPage.ets 恰好排在其后被截掉**，而 pageMap 就写在 SplashPage.ets 里；`main_pages.json` 又只有 `pages/SplashPage`。拿不到真实注册表，它转而沿用当时工程内已有的成文先例——TemplatePreviewPage.ets:338 的尾注「路由名应为 'PPTTemplatePreviewPage'（与 struct 名不同）」，即"路由名 = Android 类名"——于是写成 Android 类名 `PPTFilePage`。而 `'PptFilePage'` 早在 4 小时前（2026-07-24T02:39:56Z，batch2-closer）就已按 struct 名注册进 pageMap，两条约定在同一个 pageMap 里并存，converter 只看到了错的那条。

生成时为什么没做好: 卡在 converter 的"路由名取值"这一环——它用 `grep … | head` 的截断输出代替权威路由表，没读到 SplashPage.ets 的 pageMap，落到了「路由名=Android 类名」的旧先例上；下游 batch9-closer 的收口只做了编译 + pagemap_added 核对，而字符串路由名编译不报错，于是无人拦截。

是否必要: 必要（主改动）—— pushPathByName 用未注册名不抛错、navDestination 走不到任何分支，"作品"Tab 点卡片会静默无跳转；附带的图标 24→12x19 改动属视觉对齐判断，存疑。

证据(每条带位置):
  1. 修复 Edit：`subagents/agent-a68daf720e780b4c2.jsonl:244`（toolu_01EBTNS6KpUb25SiePfRfFBy, 2026-07-26T20:54:51.158Z）`'PPTFilePage'`→`'PptFilePage'`；结果确认 :245。
  2. 工单原文（含三点静态对照 + Android 锚点 WorksFragment.kt:265）：`subagents/agent-afcfbf677a4e5864a.jsonl:169`（vv-static-B，Write toolu_01QqmGPVHL2MCShD6rBQ6GSw, 2026-07-26T17:58:36.348Z）。
  3. 生成侧首写：`9b3105a2-…/subagents/agent-aconv-worksfrag-83d07f1d60db1b6b.jsonl:78`（Write toolu_012ZhYTocYSUCB4NaL7iSR6A, 2026-07-24T06:30:51.557Z）。
  4. 那条截断的查名 grep 与其返回：同文件 `:63`（toolu_01PJhQg8WFP5xeTv8ynbY7M5, 06:25:38.842Z）/ `:64`（uuid 06b6b779-76ab-415f-8e43-53d4ff850bc4, 06:25:39.026Z）—— 文件清单 10 条止于 RefundProgressPage.ets，无 SplashPage.ets；`main_pages.json` 仅 `pages/SplashPage`。
  5. 被沿用的错误先例（"路由名=Android 类名"）：同 `:72` 结果里 TemplatePreviewPage.ets 尾注 + `agent-abatch2-closer-0cd2cc98e7736f2f.jsonl:72` 里 pageMap 的 `name === 'PPTTemplatePreviewPage'` 分支注释。
  6. 真实注册名的写入时间早于笔误 4 小时：`agent-abatch2-closer-0cd2cc98e7736f2f.jsonl:72`（toolu_01YSwurEEBEUf34W4FjWzNYS, 2026-07-24T02:39:56.487Z）新增 `} else if (name === 'PptFilePage') { PptFilePageBuilder() }`。
  7. 收口只看编译不看路由字面量：`agent-abatch9-closer-693812e380c70c36.jsonl:195`（2026-07-24T06:53:30.122Z）报 build_status PASS / pagemap_added / slot_wired，全程无 push 名与 pageMap 的交叉核对。
  8. 附带的图标批改及其落地：`agent-a68daf720e780b4c2.jsonl:506`（toolu_01FzrLwPvf68rztxVPa2m7Gc, 2026-07-26T21:22:04.214Z，脚本内 targets 含 `WorksComponent.ets:686`）→ 结果 `:507` "ok …/WorksComponent.ets"；改后编译 `subagents/agent-af0e3d2ae54dbf769.jsonl`(build-verify-r1) 末条 2026-07-26T21:47:53.546Z BUILD_STATUS: PASS。

无法确认的部分:
  - 该 bug 从未在设备上复现过。工单自述本页 `blocked_reason=data_precondition_missing`（测试账号无作品、生成链被额度闸拦截、无 Android 基线），判定纯属静态验收；修复后也只有编译验证，转录里没有"点作品卡片跳成功"的运行时截图或 hdc 记录。
  - conv-worksfrag 是否"确实是因为 head 截断才没看到 pageMap"——只能由它的工具输出推断，它没有在文本里说明取名理由，不排除它本就打算沿用类名约定。
  - `.width($r('app.float.dp_24'))` 原始写入的确切行号未逐行取证（仅凭 conv-worksfrag 的 resources_referenced 列出 `app.float.dp_24` 与 `icon_titlebar_back_black` 反推）；36x57px 这个资源固有像素值出自 fixer 的脚本注释，未在转录里见到独立测量记录。

置信: 高 —— 修复动作、工单依据、原始写入者与那条截断 grep 的输入输出都在转录里直接可读且时间线自洽（02:39 注册 → 06:25 查名截断 → 06:30 写错 → 06:53 收口漏检 → 两天后静态验收发现）；仅"运行时是否真的无跳转"和图标尺寸那一条属未验证推断。
```