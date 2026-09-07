```
文件: entry/src/main/ets/components/common/DesignTokens.ets  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2,其自身 v4)  修复版本: v2
修复改了什么: 在 Palette 末尾新增共享常量 `DIALOG_MASK: string = '#8C000000'`(α≈0.55)并附注释,要求每个 `new CustomDialogController(...)` 显式带上它;纯新增 10 行,未动 v1 任何一行。
修复的依据: 派发词与 `spec/fix/round-1/ui/_systemic/SYSTEMIC_dialog-mask-too-light.md@v1`(主会话 v79 写, #24192@L1661)——§2/§3 三处实测蒙层像素 安卓 255→115(α≈0.55) vs 鸿蒙 255→204(α≈0.20),§5.2 明确"建议抽共享常量";fixer 另行核了安卓源码(#25040 输出 `BaseDialogFragment.dimAmount=0.55f`、`AppLoadDialog dimAmount=0.0f`)。
被改代码的来源: 纯新增(sessions 行级归属"纯新增 10 行")。v1 由 base6-common v1(#4195@L163, T+23:09)建;它没写这个 token,因为派发词 §1 把 token 取值源限定为 `resources/base/element/{color,float}.json` + `spec/magic-numbers-report.md` 高频字面量,它自己在 v1 文件头又立了"不发明设计值,没有 Android 出处的数值不进 token 表"——而 Android 的 `dimAmount` 是框架默认,不在任何资源表里;search「dimAmount」在 base6-common 全生命周期(≤v31)零命中。
生成时为什么没做好: 断在"组件层把契约写成注释、接线层各自决定"这一环——正确值生成期就有(`CustomerServiceDialog.ets@v1:303` conv-custdialog 写在"调用方约定"注释块里、`F020ViewModel.ets@v1:107` slice1-uibase 同源注释),但从没进共享 token,于是 slice9-webview 在 `CustomerServicePage.ets@v21` 落了 0.55,slice11-startup 在 `SplashPage.ets@v38` 建的隐私弹窗 controller 却一直没 maskColor。
是否必要: 必要,ArkUI 默认遮罩实测比安卓浅一半以上且跨 3 弹窗复现,值有安卓源码 `dimAmount=0.55f` 背书;放进 token 是防止再次逐窗漂移的最小改动。
证据(每条带坐标):
  1. DesignTokens.ets@v2 diff:新增 `Palette.DIALOG_MASK = '#8C000000'`,写者 fixer-r1 v4(#25015@L68 T+80:32),写前只读了 v1 的 142-196 行(#25013@L66)。
  2. SYSTEMIC_dialog-mask-too-light.md@v1:42-47 给出 255→115 / 255→204 的双端像素采样,:63 静态盘点 5 个漏设 controller,:69-72 直接点名"抽 DesignTokens 共享常量"。
  3. fixer 的安卓复核:#25041 那次 `grep --include=*.kt dimAmount` 实际报 `no matches found`(零结果),真正的依据来自 #25040 与 #25042 读到的 `BaseDialogFragment` / `MyCreatePptMoreDialog.kt:119`。
  4. base6-common 派发指令 §1 与 DesignTokens.ets@v1 文件头"取值来源(三条)"——只有资源表 / 控件源码 / magic-numbers-report,无运行时框架默认这一类。
  5. 否定证据:search「dimAmount」in base6-common ≤v31 = 0 命中;它读过的 `.claude/skills/arkts-component-builder/references/v2-dialogs-and-sheets.md@v1`(#4165@L129)全文无「maskColor」。
  6. 生成期已有正确值但只是注释:`CustomerServiceDialog.ets@v1:291-305`(conv-custdialog v1, #7767@L133 T+20:04)整段是给"调用方"的形态约定,第 303 行 `// maskColor: 'rgba(0,0,0,0.55)' // dimAmount = 0.55f`。
  7. 接线分叉:`CustomerServicePage.ets@v21`(slice9-webview v23, #22672@L260)真写了 0.55/0.0;`SplashPage.ets` 52 个版本内「maskColor」零命中,其 privacyDialogController 由 slice11-startup v22 建于 v38(#17251@L236)——正是被报的 LaunchAgreementDialog。
无法确认的部分: fixer v5 用 `/tmp/patch_mask.py`(#25093@L103,脚本黑盒)批改 51 个 controller,各调用点最终是 import `Palette.DIALOG_MASK` 还是内联字面量,账本无法逐个确认;三张 `ALIGN_*_dialog-mask.md` 在账本里是"外部输入/只被脚本碰过",visual-verify 的原始采样过程只能通过 SYSTEMIC 卡转述看到;AppTipsDialog / PayAgreementDialog 两处 controller 的生成期写者未逐一核。
置信: 高。修复内容、依据文档、v1 写者的取值规则与其"零见过 dimAmount"的否定证据、以及注释→接线丢失的两条对照链(CustomerServicePage 有 / SplashPage 无)都有直接坐标;仅批改脚本内部与像素采样原文是黑盒,不影响上述结论。
```