```
文件: entry/src/main/ets/components/HomeTabComponent.ets  修复方: visual-fixer / fixer-r1(agent-a68daf720e780b4c2, agentType=visual-fixer)  修改时间: 2026-07-26T20:47:22.889Z (uuid 0afa5ec5-e584-4244-908f-86080a3dfc35)
修复改了什么: 给顶部横幅 `Image($r('app.media.icon_home_top_bg'))` 补了 `.aspectRatio(1080 / 660)`（保留 `.width('100%')` 与 `ImageFit.Contain`），并写入 5 行注释说明 ArkUI 不等价 Android `adjustViewBounds`、实测比例 0.507 vs 固有 0.611。
修复的依据: 修复轮 finding `spec/fix/round-1/ui/ALIGN_PHomeFragment_layout_drift_header-banner-height.md`——安卓基线紫色头图到屏高 23.9%、鸿蒙只到 17.3%，dump 节点 `Image[0,127][1216,743]` 高宽比 0.507 ≠ 资源固有 660/1080=0.611；§5 直接建议 `.aspectRatio(1080/660)`。修复前该 agent 已按纪律读了 sbs 拼图并用 sips 核过资源像素 1080x660。
被改代码的来源: 生成轮 conv-hometab（customAgentType `a2h-activity-converter`）2026-07-24T03:16:15.614Z 一次性 Write 生成，写的是 `.width('100%').objectFit(ImageFit.Contain).alignSelf(ItemAlign.Start)`（1 分钟后又删掉 alignSelf）。它的显式依据是 pitfalls 库的 **P-15「Android ImageView 默认 FIT_CENTER → objectFit(Contain)」**——该规则只管裁切方式，不含"adjustViewBounds → 需显式高度/aspectRatio"，所以高度整条被漏掉；此后生成轮无任何 agent 再动过这个 Image 块。
生成时为什么没做好: 卡在"规则库 + 基线快照"这一环——`ui-migration-pitfalls.md` 的 P-15 缺 adjustViewBounds→高度映射，而 page_0010_HomeFragment 的 view.xml 是 `synthesized="true"`、所有 `bounds=""`，转换器既无规则可依也无实测高度可抄（自己在文件头注明 confidence=medium / 不硬编码 bounds D-008），只能落成"宽 100% + Contain"。
是否必要: 必要——`aspectRatio(1080/660)` 使高度回到 width×0.611，正好消掉实测 0.507 的压扁，且不改资源、不改布局结构。
证据(每条带位置):
  1. 修复动作: ff019d8a-.../subagents/agent-a68daf720e780b4c2.jsonl:176（2026-07-26T20:47:22.889Z）Edit，old=`.width('100%')/.objectFit(Contain)` → new 增 `.aspectRatio(1080 / 660)`；:177 返回 updated successfully。
  2. 修复依据原文: 同文件 :171 Bash（20:46:38）批量 cat findings，:172 tool_result 含 §3「头图节点 Image[0,127][1216,743] 高宽比 0.507 vs 固有 0.611」+ root_cause_hint 指名 `HomeTabComponent.ets:369-371` + §5「推荐 .aspectRatio(1080/660)」。
  3. 依据的可信度锚点: 同文件 :36（20:34:06）Read `spec/visual-verify/screenshots/sbs/round-1/trip_1_logged_out/HomeFragment.jpeg`（满足 finding 的「FIXER MUST READ 拼图」纪律）；:122/:123 sips 实测 `icon_home_top_bg.webp pixelWidth:1080 pixelHeight:660`。
  4. finding 作者: ff019d8a-.../subagents/agent-a8ef23a1c410ba9c9.jsonl:273（2026-07-26T20:17:32.197Z，meta name=vv-t2-A03「Phase4 batch trip2_A03」）Edit 填入 §2/§3；:298（20:20:16）把 suggested_files 由 `HomeComponent.ets` 改正为 `HomeTabComponent.ets`。
  5. 原写者与原文: 9b3105a2-.../subagents/agent-aconv-hometab-afeccbf00da93597.jsonl:57（2026-07-24T03:16:15.614Z，uuid 05c58ac5）Write 全文，注释「imageView2：match_parent 宽、adjustViewBounds 按比例、贴顶」下只写 width+Contain；:63（03:17:13）仅删 `alignSelf`。同 agent 的完工报告自述遵循「P-15 所有 Image 显式 objectFit(Contain)」。
  6. 规则库缺口: 同 agent :49 Read `.claude/skills/android-ui-graph-query/references/ui-migration-pitfalls.md`，:50 结果里 P-15 全文只有「默认 FIT_CENTER→Contain」四行，全文无 adjustViewBounds / aspectRatio 字样。
  7. 同轮兄弟 agent 反证: 9b3105a2-.../subagents/agent-aconv-homedoc-d395ee6a88c25d38.jsonl:64（2026-07-24T03:15:19.385Z，比 hometab 早 1 分钟）对 icon_home_title 写了 `.aspectRatio(488 / 68) // 固有 488x68px 宽高比（adjustViewBounds 等价）`——正确映射当时只存在于个别 agent 的临场判断，未沉淀成共享规则。
无法确认的部分: finding §5 第 3 步「复核步骤条白卡 margin，使白卡上沿仍压在紫色区内」在本次修复里没有对应改动（该 agent 之后对 HomeTabComponent 的编辑 :307/:361/:364 分别是 PermissionIntroHost、Tab 热区/步骤1文案、注释，与本 finding 无关）；修复后是否真的把紫→灰过渡推回 23–24%（round-2 复测结果）本目录未查证；文件当前磁盘内容无法读取，只能依据转录中的 Edit 记录。
置信: 高——修改、依据文档、原始 Write、所依规则原文、以及规则缺口的反证样本都能逐条定位到转录行与时间戳，且生成轮该代码块只被写过一次、无中间改写者。
```