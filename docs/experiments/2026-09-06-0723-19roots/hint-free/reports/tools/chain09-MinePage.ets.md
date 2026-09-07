```
文件: entry/src/main/ets/pages/MinePage.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v40
修复改了什么: 给 header() 的外层 Stack 补 `.height(128)` + `.clip(false)`（128 = 头像 marginTop 60 + 头像 68），让 1080x648 的装饰头图 icon_mine_top_bg 不再决定头区高度、只作溢出的背景层。
修复的依据: spec/fix/round-1/ui/ALIGN_PMineFragment_layout_drift_header-height.md@v1（fixer-r1 v7 读，#23143）§3 实测「VIP 横幅及以下整体下移约 117vp、续订管理/关于我们被挤出首屏」，§5 处方逐字就是「外层 Stack 显式约束 60+68=128vp」+「给 Stack 设 .clip(false) 保留装饰图下溢」；上位单 spec/fix/round-1/ui/_systemic/SYSTEMIC_image-no-explicit-size.md@v2（fixer-r1 v1 全文读）给出同根定性。
被改代码的来源: 纯新增（blame v40 changed=True：替换 0 行、新增 4 行）。前一版 v39 写者是 slice17-home v29（#17632），其派发词只授权「填 HomePage 四槽位 + 接 F018ViewModel、已有 UI 勿新建」，不含布局改写，故没写高度。被它包住的那个无高度 Stack 出自生成期 conv-mine v1 写 MinePage.ets@v1（#8263），依据是全文读 fragment_mine.xml@v1（#8214）+ activity_mine.xml@v1 + page_0017_MineActivity.md@v1，转换决策见其收尾报告：「ConstraintLayout → Column + Stack（P-07 约束表达力缺口；头图/横幅叠加区用 Stack）」与「未标注尺寸的图标留固有尺寸 + Contain，交 icon-sizing 自愈——不硬编码 bounds（confidence=medium）」。
生成时为什么没做好: 转换错——conv-mine v1 源码读全了，却在 ConstraintLayout→Stack 这一环把 `iv_vip_enter` 的 `layout_constraintTop_toBottomOf="@id/iv_user_icon"` 链丢成无约束叠放，并把尺寸缺口寄给一个实际不存在的「icon-sizing 自愈」环节。
是否必要: 必要，同一处缺陷在被实测的孪生文件 MineComponent.ets@v30 上已按同一处方修复，MinePage.ets 是 D0 下不合并的同构副本，不改则该页复现同一 117vp 位移。
证据(每条带坐标):
  1. diff MinePage.ets@v40：仅 +`.height(128)` +`.clip(false)` 两行属性 + 两行注释；blame MinePage.ets@v40 changed=True = 替换/删除 0 行、新增 4 行。
  2. ALIGN_PMineFragment_layout_drift_header-height.md@v1（action fixer-r1 #23143 原文）§4 源码缺口点名「header() 的 Stack 内 Image(icon_mine_top_bg).width('100%').objectFit(Contain) 无高度约束」，§5 给出 128vp + clip(false)。
  3. conv-mine 收尾报告（agent conv-mine v8）的「Component Mapping Decisions / 尺寸策略」两条，即该 Stack 无高度、图标无尺寸的原始依据；同 agent v1 的读取集含 fragment_mine.xml@v1 全文（#8214），属「读全了仍写错」。
  4. fixer-r1 v12 的补丁脚本（action #23177）以 `assert s.count(old)==1` 命中的 old_string 仍带生成期原注释「icon_mine_top_bg：顶部装饰头图（match_parent + adjustViewBounds → 满宽、按固有比例，P-15 需 Contain）」——说明 v1 那段代码到 v39 未被任何人改过。
  5. index(query="icon-sizing") 返回 agent 0 / 文件 0 —— 账本里从没有过「icon-sizing 自愈」这个环节，conv-mine 依赖的下游兜底不存在。
  6. diff MineComponent.ets@v30（fixer-r1 v11）是同一处方的孪生改动，佐证 MinePage.ets@v40 不是孤立臆改。
无法确认的部分: MinePage.ets@v39 的逐行归属因 v17/v18 之间的 edit-miss 断点标为「归属未知(断点后)」，头区那几行的作者是靠 conv-mine 收尾报告 + 补丁 old_string 间接坐实，不是逐行签名；MinePage.ets 本身没有独立的 finding 或双端截图（visual-verify 只覆盖 page_0016 MineFragment/MineComponent），该页是否已注册进 pageMap、实际可达性无法从本次证据确认；v10–v31 多版内容未知，期间是否有人碰过头区无法核。
置信: 中——修复内容、依据与孪生改动三方互证且坐标齐全，但被改区域的逐行归属被断点挡住，生成期作者是间接坐实而非签名，且 MinePage 这一副本缺自己的实测证据。
```