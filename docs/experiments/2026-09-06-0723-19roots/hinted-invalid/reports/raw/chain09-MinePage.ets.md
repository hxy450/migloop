```
文件: entry/src/main/ets/pages/MinePage.ets  修复方: visual-fixer(agent-a68daf720e780b4c2，name=fixer-r1，agentType=visual-fixer)  修改时间: 2026-07-26T20:45:36.733Z（Edit toolu_01AczYkHyvRAYuGaP8Dn7MNi）

修复改了什么: 给 header() 最外层 Stack 补 `.height(128)` + `.clip(false)`（并附注释「60 marginTop + 68 头像 = 128vp，对位安卓 iv_vip_enter 的 constraintTop_toBottomOf=iv_user_icon」）；同一批次前 21 秒（20:45:15，line 152）还把同一个 header 里的装饰头图从 `.width('100%').objectFit(Contain)` 改成加 `.aspectRatio(1080/648)`，并把 4 个宫格图标 48x48、右箭头 12x12+flexShrink(0)、VIP 字标按会员态 121x20 / 160.7x19 全部写死。

修复的依据: round-1 finding `ui/ALIGN_PMineFragment_layout_drift_header-height.md` §5 建议 1、2 —— 原文就给了「在外层 Stack 上显式约束高度为 60+68=128vp」和「给 Stack 设 .clip(false) 保留装饰图下溢」；其 android_anchor 是 `app/src/main/platform-res/layout/fragment_mine.xml:60-68 iv_vip_enter app:layout_constraintTop_toBottomOf="@id/iv_user_icon"`，实测差异为「横幅顶边 148dp→265vp，以下整体下移约 117vp，续订管理/关于我们被挤出首屏」。fixer 在改前按单里的强制要求读了 sbs 拼图 MineFragment.jpeg（line 34-35，20:34:05）。注意：该单 §4 只点名 `MineComponent.ets:389-437`，MinePage.ets 是 fixer 自己判定的「同构孪生体」而顺手同改（line 149：“the standalone-page twin of MineComponent”）。

被改代码的来源: 生成轮子 agent `conv-mine`（agent-aconv-mine-bb78af185c44860a，customAgentType=a2h-activity-converter，opus），2026-07-24T05:10:11.321Z 一次性 Write 整个 MinePage.ets（line 82）。它在 04:58:23（line 38）读了源布局 XML 全文，`iv_vip_enter` 的 `layout_constraintTop_toBottomOf="@id/iv_user_icon"` 就在它读到的第 68 行里；但它按 P-07（ConstraintLayout → 拆 Column/Row+Stack）把约束链拍平成线性 Column，header 的 Stack 只写了 `.width('100%')`、不定高，装饰头图只按 P-15 补了 `objectFit(Contain)`——即「本次新增的 .height(128) 是纯新增」，前一版没写是因为它认为 Stack 走 wrap-content 即可。

生成时为什么没做好: 缺陷在生成链路的「转换规则手册」这一环——pitfall 目录里 P-15 只说了 Image 的缩放默认值（Cover→Contain，line 61 转录 169-173 行），**没有任何一条说 ArkUI Image 不写 width/height 时撑满父容器**，也没有「ConstraintLayout 拍平会丢掉装饰层不参与链式定位」的守卫，于是 conv-mine 逐字执行规则也必然写出这段代码（它自评报告 line 125 还把「P-15 全部 objectFit(Contain)」列为已完成项）。

是否必要: 必要 —— 安卓真值 148dp 与鸿蒙实测约 265vp 的差是页面级信息缺失（末两条设置项掉出首屏），不定高就修不掉；但 `.clip(false)` 是 ArkUI 默认值，属冗余保险。

证据（每条带位置）:
  1. 本次 Edit 的 old/new 全文：ff019d8a-.../subagents/agent-a68daf720e780b4c2.jsonl:156，2026-07-26T20:45:36.733Z，new_string 含 `.height(128)` + `.clip(false)` + 128=60+68 的推导注释。
  2. 同批次前置改动（aspectRatio(1080/648)、48x48、12x12、字标双态尺寸）：同文件 line 152，20:45:15，Bash python 补丁，改前源码形态见 line 151 的 sed 回显。
  3. 依据 finding 原文（期望 148dp / 实测 265vp / §5 明写 128vp 与 clip(false)）：同文件 line 120 的 tool_result，20:42:11.975Z（fixer 在 line 119 用 sed 一次读了 4 张 MineFragment 单）。
  4. 读图纪律已执行：同文件 line 34-35，20:34:05，Read `spec/visual-verify/screenshots/sbs/round-1/trip_1_logged_out/MineFragment.jpeg`。
  5. 被改代码的原始作者与时间：9b3105a2-.../subagents/agent-aconv-mine-bb78af185c44860a.jsonl:82，2026-07-24T05:10:11.321Z，Write MinePage.ets（17916 字节），header() 的 Stack 尾部只有 `.width('100%')`。
  6. 原作者确实看过那条 ConstraintLayout 约束：同文件 line 38，2026-07-24T04:58:23.676Z 的 XML 全文，第 60-68 行 `iv_vip_enter ... layout_constraintTop_toBottomOf="@id/iv_user_icon"`。
  7. 规则手册的缺口：同文件 line 61，2026-07-24T05:01:12.685Z，pitfall 文档 169-173 行 P-15 全文只讲 ScaleType/objectFit；该 agent 的自陈规则清单见 line 65（“P-15(Image 默认 Cover→需 Contain)、P-07(ConstraintLayout→拆 Column/Row+Stack)、P-13/P-17(Stack z-order)”）。
  8. 修复方对 MinePage 的定位是自行外推：同 fixer 文件 line 149（20:44:51.198Z）与 line 601 的 attempt 记录「MinePage.ets（同上 5 处，MineComponent 的独立 Activity 孪生体）」。

无法确认的部分: ① MinePage（MineActivity 独立入口）本身在 round-1 里**没有**任何截图或 finding，它的 128vp 是从 MineFragment 的实测差异外推的，本轮转录里查不到对 MinePage 的视觉复测；② 生成轮是否有 closer/reviewer 曾复查过 MinePage 的 header 并放行，我只确认了 12 个 batch-closer 转录里出现过 `icon_mine_top_bg`，没有逐个核对它们是否针对本处做过判定；③ `.height(128)` 是否会因文案列高于 68vp 而反过来裁掉昵称行，转录里无复测证据（单里明令 fixer「不重编、不复测」，见 fixer prompt line 1「收尾（严格）」）。

置信: 高 —— 改动、依据单、原始 Write 与规则手册缺口四点都能落到具体行号和时间戳，且 fixer 自己写的 attempt 记录与转录中的实际 Edit 内容互相印证；仅 MinePage 侧的效果验证缺证据，已单列。
```