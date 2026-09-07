```
文件: entry/src/main/resources/base/element/color.json（色值条目 color_home_tab_bg，文件内 180-181 行）
修复方: visual-fixer「fixer-r1」(subagent agent-a68daf720e780b4c2，toolUseId toolu_01APi9vUJuvdDSBK2JqMebM4，父会话 ff019d8a 修复轮)
修改时间: 2026-07-26T20:34:44.842Z（uuid 0cbdf359-1d1f-4e8c-aaf8-a4bc1d46dbbf）

修复改了什么: 把 `color_home_tab_bg` 的值从 `#ff202022`（近黑）改成 `#ffFFFFFF`（纯白），并同步订正 HomePage.ets:11 与 :461 两处「深色底栏 #202022」的注释，使首页底部 4-Tab 栏由深色变白色。

修复的依据: round-1 视觉核验单 `SYSTEMIC_home-tab-bar-dark-background`（affects 4 条 `ALIGN_P{Home,Recommend,Works,Mine}Fragment_color_mismatch_bottom-tab-bg`），android_anchor 为 `app/src/main/res/layout/activity_home.xml:21 ll_bottom_tab android:background="@color/white"`；单里直接给出修复建议「`color.json` 的 `color_home_tab_bg` 由 `#ff202022` 改成 `#ffFFFFFF`（一处改动即修 4 页）」。fixer 落盘前 grep 确认该 token 全工程只有 HomePage.ets:461 一个消费者。

被改代码的来源: 值本身是生成轮 stage0-resources（agent-astage0-resources-a72c95c804e188d5，2026-07-24T01:36:29）对安卓 `app/src/main/res/values/colors.xml` 的 1:1 忠实搬运——安卓那份 colors.xml 里确实写着 `<color name="color_home_tab_bg">#202022</color>`（注释「首页底部背景颜色」）。真正的错在引用侧：aconv-home（2026-07-24T02:04:42，L68）写下 `.barBackgroundColor($r('app.color.color_home_tab_bg')) // 深色底栏 #202022`，它已在 L18 读到 activity_home.xml:21 的 `@color/white`，仍作出「底栏配色冲突裁决」，理由是「未选中 #D1D5EB 浅色文字在白底不可见 + resource-mapping.md 锚定深色 + 与 team-lead 指令一致」，主动否决了布局真值。该 token 在安卓侧其实是废弃/未被布局引用的死资源。

生成时为什么没做好: 断在「设计令牌表」这一环——team-lead 只按 colors.xml 的资源名和注释推断语义（主会话 L520 令牌表「首页 Tab 背景 #202022（深色）」），把它固化进 F018 验收标准（L1378「底部导航背景为深色 #202022」）和派单指令（L1925「底部导航深色背景 $r('app.color.color_home_tab_bg')(#202022)」），converter 面对布局真值与上游指令冲突时选择服从指令，于是错误被三层背书、无人回查 layout 的实际 background。

是否必要: 必要——布局真值 + 侧对比截图双证，且是 4 页共用的同一行代码；唯一保留意见是它改的是共享 token 值（使 color.json 与安卓 colors.xml 不再逐值对齐），改引用为白色资源本可同时保住资源映射一致性。

证据（每条带位置）:
  1. 修复动作：agent-a68daf720e780b4c2.jsonl:54（Edit `#ff202022`→`#ffFFFFFF`，2026-07-26T20:34:44.842Z）；同文件 :58、:62 改两处注释。
  2. 改前唯一消费者核查：agent-a68daf720e780b4c2.jsonl:44-45（grep 结果只有 color.json:180 定义 + HomePage.ets:11 注释 + :461 引用）。
  3. 修复依据单原文：agent-a68daf720e780b4c2.jsonl:27（读到单的 §2-§5，含 anchor `activity_home.xml:18-24 android:background="@color/white"`、「一处改动即同时修复 4 页」）。
  4. 单的产出方与取证：agent-a96b301d9764dca23.jsonl:392（vv-t1-A02 用 render_finding_skeleton 生成 4 条 finding，2026-07-26T16:55:16）；:77 读到 activity_home.xml 原文 `android:background="@color/white"`；:62-63 先读了 sbs 对比截图 `spec/visual-verify/screenshots/sbs/round-1/trip_1_logged_out/HomeFragment.jpeg`（16:02:15），即截图+源码双证。
  5. 被改值的出处：agent-astage0-resources-a72c95c804e188d5.jsonl:43（2026-07-24T01:36:29，读到安卓 colors.xml 内 `color_home_tab_bg #202022`）；:203 的 resource-mapping 表把它登记为 `#ff202022`。
  6. 错误引用的写者与自述裁决：agent-aconv-home-2cc89a9fca55ecb2.jsonl:18（已看到 activity_home.xml:21 `@color/white`）、:68（写下深色 barBackgroundColor）、:83/:85（明写「底栏背景冲突裁决……采用 color_home_tab_bg，与你的指令一致」）。
  7. 上游指令链：主会话 9b3105a2-*.jsonl:520（令牌表「#202022（深色）」）、:1378（F018 AC「底部导航背景为深色 #202022」）、:1925（派给 aconv-home 的任务卡「底部导航深色背景 …(#202022)」）。
  8. 错误随后被固化传播：agent-aslice17-home-cbf5a21e1ea6963a.jsonl:218（2026-07-24T19:44 重写 HomePage 时原样保留该行及注释）。

无法确认的部分:
  - 安卓 4 个 ShapeTextView 的 textColor selector 是否真的用 `color_text_home_tab_unselected(#D1D5EB)`——converter 的「白底浅灰不可见」论据成不成立无法从转录直接证实；vv agent 只 grep 到 colors.xml 的定义（agent-a96b301d9764dca23.jsonl:81-82），未展示 selector 文件。
  - 是否存在 `resources/dark/element/color.json` 同名 key（单的建议第 4 条）——fixer 转录中未见核对。
  - 修复后未复测：fixer 任务卡明确「不重编、不复测」（agent-a68daf720e780b4c2.jsonl:1），改后视觉是否转 fixed 需下一轮验证，本转录内无结果。

置信: 高——修改动作、依据单、单的取证过程、原始值的搬运方、错误引用的写者及其自述裁决、以及上游指令三处出处，均在转录里逐条对上且时间线自洽；仅次要论据（文字色 selector、dark 目录）缺证。
```