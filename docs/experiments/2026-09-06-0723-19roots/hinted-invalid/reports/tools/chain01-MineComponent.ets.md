```
文件: entry/src/main/ets/components/MineComponent.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v26/27/28/29/30
修复改了什么: 给本文件 4 处只写了 `.objectFit(ImageFit.Contain)`、没写尺寸的 Image 补上显式宽高（设置行右箭头 12×12、服务宫格 48×48、VIP 字标 160.7×19 / 121×20、头图 `aspectRatio(1080/648)`），并把头区 Stack 从「由装饰图撑高」改成钉死 `.height(128) + .clip(false)`。
修复的依据: `SYSTEMIC_image-no-explicit-size.md@v2` §3/§4（P0：ArkUI Image 不写宽高不取固有尺寸而撑满父容器；箭头撑满行宽把 `layoutWeight(1)` 左标题压成 0 宽 → 7 条设置文案整体不渲染），fixer-r1 v1 读入；尺寸值来自 fixer-r1 v7 #23148 用 `sips` 实测的 drawable 像素 ÷3；另读了 4 张 `ALIGN_PMineFragment_*` 单(#23143)。
被改代码的来源: 生成方 conv-minefrag(agent-aconv-minefrag-0c34d8c25c9daec8) v1 #8360 写 MineComponent.ets@v1 时按迁移坑位指南写的——其收尾报告列 “P-15（4 处 Image 显式 Contain）”“P-13/P-17（Stack z-order）”，与被删注释「（P-15 需显式 Contain）」「// Stack z-order（P-13/P-17）」四处逐一对应；行级签名因断点不可考（见证据 6）。
生成时为什么没做好: 指南 `ui-migration-pitfalls.md@v1` 的 P-15 只写「Android FIT_CENTER vs ArkUI 默认 Cover → 设 objectFit(Contain)」，缺「不写 width/height 会撑满父容器」这条不变量，转换 agent 照单全收 —— spec 写错（不全）在生成链最上游的坑位库那一环。
是否必要: 必要，设置行箭头那处是 P0（直接导致 7 条文案不可见），尺寸值有实测取证；只有头区钉死 128vp 一处的取值依据在实录里无法复核。
证据(每条带坐标):
  1. diff MineComponent.ets@v26–@v30：v26 箭头补 12×12+flexShrink(0)、v27 宫格图标补 48×48、v28 VIP 字标按 isVip 二态补 160.7×19 / 121×20、v29 头图补 aspectRatio(1080/648)、v30 Stack 补 .height(128).clip(false)。
  2. `spec/fix/round-1/ui/_systemic/SYSTEMIC_image-no-explicit-size.md@v2` 第 52-53、57、65-68 行：点名「固有尺寸交 icon-sizing 自愈」这类注释「假设本身是错的」，MineComponent 设置行箭头列为 P0；fixer-r1 v1 全文读入。
  3. fixer-r1 v7 #23148（sips 实测）：icon_mine_right_arrow 36×36、四宫格图标各 144×144、icon_txt_have_open_vip 482×57、icon_txt_open_vip 363×60、icon_mine_top_bg 1080×648 —— ÷3 正是 v26–v29 写入的值。
  4. conv-minefrag v1 #8337/#8339 读 `.claude/skills/android-ui-graph-query/references/ui-migration-pitfalls.md@v1`，P-15 原文四行全文只有「ArkUI 默认 Cover → 修复：设置 .objectFit(ImageFit.Contain)」，无任何「缺省尺寸」条款（同文件 P-20/P-22 只覆盖 '100%' 子节点与滚动容器，覆盖不到 Image）。
  5. conv-minefrag v2 收尾报告 “Pitfalls: …P-15（4 处 Image 显式 Contain）” —— 数量与被修复的 4 处 Image 站点一一对应。
  6. blame(MineComponent.ets, v26/27/28/29, changed=True)：被替换的 4 行全部「归属未知(断点后)」，因文件有 edit-miss 断点 @2026-07-24T16:30（group2-closer 写的 v14–v18 内容未知）。
  7. index(kind=agent, query="icon") 返回 0 个 agent —— 注释所指望的 “icon-sizing 自愈” 环节在整本账里根本不存在，即无人会替它补尺寸。
无法确认的部分: ① 4 行被删注释的确切写者（断点后行级归属未知，只能由 conv-minefrag 收尾报告逐处对应推定，group2-closer v14–v18 是否改写过措辞无从核对）；② `ALIGN_PMineFragment_layout_drift_header-height.md@v1` 是外部输入、内容无法复原，且 fixer-r1 v7–v11 窗口内未见读 `fragment_mine.xml`，故 v29/v30 注释里「iv_vip_enter constraintTop_toBottomOf @id/iv_user_icon(:68) + marginTop 20dp」与 60+68=128vp 的原始出处不可复核；③ MineComponent.ets 在 fixer-r1 v16 #23238 还被一次「脚本黑盒」碰过，方向不明，是否二次改动无法确认。
置信: 高 —— 改了什么、凭什么改（单 + sips 实测）、原写者凭什么写（P-15 原文）三段都有直接工具坐标，唯一薄弱处是行级签名被断点抹掉，靠生成方收尾报告的逐处对应补位。
```