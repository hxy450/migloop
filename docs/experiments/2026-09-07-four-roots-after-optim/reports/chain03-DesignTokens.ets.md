```
文件: entry/src/main/ets/components/common/DesignTokens.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v2
修复改了什么: 在 Palette 末尾纯新增 10 行 —— 常量 DIALOG_MASK = '#8C000000'(α≈0.55)及注释,作为全仓 CustomDialogController 的 maskColor 共享取值;不动任何既有行。
修复的依据: 单 spec/fix/round-1/ui/_systemic/SYSTEMIC_dialog-mask-too-light.md@v1(主会话·ff019d8a v79 写),fixer-r1 v1 全文读过(#24963):安卓蒙层区像素 255→115(α≈0.55)、鸿蒙 255→204(α≈0.20),跨 2 trip / 3 弹窗复现,单的 §5.2 直接建议"抽一个共享常量 DesignTokens.DIALOG_MASK_COLOR";主会话派发词(fixer-r1 派发自主会话 @v83)也把它列为 SYSTEMIC 三条之一并写明"建议抽共享常量"。
被改代码的来源: 纯新增(sessions 行级归属"纯新增 10 行"),前一版 DesignTokens.ets@v1 由 base6-common v1 写(#4195, T+23:09)。它没写的原因是取值源清单里根本没有弹窗:派发词 §1 把 token 取值源限定为 resources/base/element/{color,float}.json + spec/magic-numbers-report.md 高频字面量,文件 v1 头注也自陈三条来源(资源表 / SettingBar.kt / 高频统计)+"不发明设计值";它在写 v1 前从未读过弹窗基类,search「maskColor」≤v1 = 0 命中。
生成时为什么没做好: 漏读 —— 安卓侧真值 BaseDialogFragment.kt@v2:47 `dimAmount = 0.55f` 全实录只有 conv-worksmore v1 读到(#12371, T+18:55),它按"页转换器不碰宿主"把窗口形态(含 maskColor rgba(0,0,0,0.55))只写成给调用方的约定注释,没人接;Base-6 建 token 表时既没读这个基类、其所读的技能文档 v2-dialogs-and-sheets.md@v1 全文也无 maskColor 一词,于是这个数值在生成链上没有落点。
是否必要: 必要 —— 它被 fixer-r1 v5 起用 /tmp/patch_mask.py(#25093)铺到 SplashPage/HomePage/MemberCenterPage/AboutUsPage/MineComponent/HomeTabComponent/PermissionIntroHost 等多处 `maskColor: Palette.DIALOG_MASK`(#25095/#25099/#25250/#25296),不加常量就是 51 处各写各的字面量。
证据(每条带坐标):
  1. diff(DesignTokens.ets@v2):+DIALOG_MASK: string = '#8C000000',写者 fixer-r1 v4 (#25015@L68 T+80:32),写前只读了自己 142-196 行(#25013)。
  2. SYSTEMIC_dialog-mask-too-light.md@v1 第 42/47/60 行:255→115 vs 255→204、根因"CustomDialogController 未显式设置 maskColor";第 71 行点名要抽 DesignTokens 常量。
  3. fixer-r1 v4 自述(#25012):"Now SYSTEMIC #3 (dialog mask). Let me add a shared token first." —— 改动动机与单一一对应。
  4. DesignTokens.ets@v1 写者 base6-common v1 派发词 §1 + 文件头"取值来源(三条)":均不含弹窗窗口属性;search「maskColor」in base6-common ≤v1 = 0 命中(可引用的否定证据)。
  5. search「dimAmount」in BaseDialogFragment.kt:首见 v2:47 `= 0.55f`,读者仅 conv-worksmore v1(#12371);其收尾报告把 dimAmount=0.55f / maskColor rgba(0,0,0,0.55) 归为"宿主 CustomDialogController 配置项…文末调用方约定"。
  6. search「maskColor」in .claude/skills/arkts-component-builder/references/v2-dialogs-and-sheets.md@v1:全文无此词 —— base6-common 读过这份弹窗范式文档(#4165),文档本身没提 ArkUI 默认遮罩与安卓 dimAmount 的差异。
  7. search「DIALOG_MASK」in fixer-r1 ≤v37:token 经 /tmp/patch_mask.py(#25093)落到 7+ 个页面/组件文件,证实被真实消费。
无法确认的部分: (a) 其余两个复现弹窗(LaunchAgreementDialog / PayAgreementDialog / AppTipsDialog)的转换者是否也留过同样的"调用方约定"注释、以及宿主页写者当时是否看见过——本次未追那几条链,无法确认;(b) 修复方用字面量 string 而非按 v1 头注约定"先进 color.json 再 $r() 转发",是否在后续构建/校验中留下问题——build-verify-r1 v6 读过 v2(#28045/#28047)但其结论未查,无法确认;(c) 单里"静态盘点 5 个漏设 controller"与 fixer 报的"51 站点"口径差异,未逐一核对。
置信: 高 —— 修复内容、依据单、消费点、以及生成侧"取值源不含弹窗 + 唯一读到 0.55f 的 agent 只留了注释"四段都有账本坐标直接对上,只有跨弹窗的旁链未展开。
```