```
文件: entry/src/main/ets/components/common/DesignTokens.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v2(agent 自身 v4,#23057 @T+80:32)
修复改了什么: 在 Palette 末尾新增共享常量 `DIALOG_MASK: string = '#8C000000'`(α≈0.55)并附注释,说明每个 `new CustomDialogController(...)` 都必须显式带上它;纯新增 10 行,未改动任何既有 token。
修复的依据: 单 `spec/fix/round-1/ui/_systemic/SYSTEMIC_dialog-mask-too-light.md@v1` §2/§3 的像素实测(安卓蒙层 255→115 ≈α0.55,鸿蒙 255→204 ≈α0.20,跨 2 trip/3 弹窗复现)与 §5.2「抽一个共享常量」的处方;修复方另做了单里没有的源码取证(#23082 全仓 grep `dimAmount`、#23083 读 `BaseDialogFragment.kt@v2` 与 `AppLoadDialog.kt@v2`),据此把 loading 那 6 处按 override=0.0f 排除。
被改代码的来源: 纯新增。前一版 DesignTokens.ets@v1 由 base6-common v1(#3359 @T+23:08)创建;其派发词把 Design Tokens 的取值源限定为「已落地的 resources/base/element/{color,float}.json + Stage 1 各页反复出现的字面量(magic-numbers-report)」,即只从鸿蒙侧既有产物归纳。蒙层色在鸿蒙侧从没人写过、也不在 color.json 里,归纳不出;base6-common 全程未读任何安卓弹窗基类,故 Palette 的 14 个 token 全是 $r() 转发,天然没有 DIALOG_MASK。
生成时为什么没做好: 断在弹窗转换环(a2h-activity-converter)——安卓的 dim 是窗口级属性、写在基类 `BaseDialogFragment.kt:47 dimAmount = 0.55f`,而转换器只读子类与 layout xml,把 `@CustomDialog`+Controller 的窗口属性整条丢了,51 个站点无一带 maskColor;DesignTokens 缺 token 只是这个丢失的下游表现。
是否必要: 必要,它是 51 个 Controller 共用的取值载体(单 §5.2 明确要求抽常量),值 0.55×255≈0x8C 与安卓基类默认值一致,不新增也就无从统一补 maskColor。
证据(每条带坐标):
  1. diff `DesignTokens.ets@v2`:仅追加 `Palette.DIALOG_MASK='#8C000000'` + 注释;file 脊柱显示 v1←base6-common v1(#3359 T+23:08)、v2←fixer-r1 v4(#23057 T+80:32),共 2 版。
  2. `SYSTEMIC_dialog-mask-too-light.md@v1`(主会话·ff019d8a v70 #22214 写)§3/§4:根因是 `CustomDialogController` 未设 `maskColor`,走 ArkUI 默认遮罩;§5.2 建议抽共享常量。fixer-r1 v1 于 #22996 全文读了它。
  3. 安卓侧真值:`BaseDialogFragment.kt@v2:47 protected open var dimAmount = 0.55f`(file content 38-55 行);fixer-r1 v5 #23082/#23083 复核了它与 `AppLoadDialog.kt`(override 0.0f)。
  4. base6-common 的派发词「Design Tokens…来源:已落地的 color/float.json + Stage 1 高频字面量」+ 其 v1 读取集(color.json@v2 / float.json@v2 / magic-numbers-report@v19,零安卓弹窗基类)→ 相对修复方是漏读,但属派发范围本身未覆盖。
  5. 转换环取证:conv-launchagree v1(转 page_0039 LaunchAgreementDialog,正是单里 page_id)#7882 全文读 `LaunchAgreementDialog.kt@v2`,该文件第 27 行 `: BaseDialogFragment<...>()`、第 33 行只 override 了 `canTouchDismiss`,dimAmount 靠继承;但它的读取集里没有 `BaseDialogFragment.kt`,派发词也只说「用 @CustomDialog 或 CustomDialogController 形态」,无窗口属性核对项。
  6. 缺口是全局的:fixer-r1 v1 #23002 全仓扫 `new CustomDialogController(` 命中 24 文件(MineComponent:146/161/179…、AccountInfoPage:138…、CustomerServicePage:183… 等),收尾报「51 个控制器全补齐」——生成期无一处带 maskColor。
无法确认的部分: 1) 转换期技能参考(`arkts-component-builder/references/v2-dialogs-and-sheets.md`、`ui-migration-pitfalls.md`)是否根本没写 dimAmount→maskColor 的映射——未展开其全文,故「知识库缺条目」只是可能而非已证。2) `BaseDialogFragment.kt@v2` 有 6 个 conv-* 转换器在生成期读过全文(conv-fileconfirm/vipbind/refundreason/renewrule 等),它们手里有 0.55 却仍未写 maskColor,属「转换错」还是同样没意识到窗口属性,账本无记录,逐个未核。3) `DesignTokens.ets@v1` 被读时多为「版本就近绑定(不确定)」,不影响本结论但精度有限。
置信: 中——修复内容、依据、v1 写者与其取值范围三项都有直接坐标可证;把根因定到「弹窗转换环丢窗口属性」只逐条验证了 conv-launchagree 一个转换器,其余站点靠全仓扫描结果与单的实测反推。
```