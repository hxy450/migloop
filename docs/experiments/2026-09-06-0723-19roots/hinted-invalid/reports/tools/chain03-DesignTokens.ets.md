```
文件: entry/src/main/ets/components/common/DesignTokens.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v2
修复改了什么: 在 `Palette` 末尾新增 10 行——共享常量 `DIALOG_MASK: string = '#8C000000'`(α≈0.55)加一段注释,说明它对位 Android Dialog 的 `dimAmount≈0.55`,供各 `CustomDialogController` 的 `maskColor` 引用。纯新增,没删改任何旧行。
修复的依据: 单 `SYSTEMIC_dialog-mask-too-light.md@v1`(fixer-r1 v1 #22996 全文读):§2/§3 三处像素实测(安卓蒙层 255→115 ≈α0.55,鸿蒙 255→204 ≈α0.20)、§4 根因判为「`CustomDialogController` 未显式设 `maskColor`」、§5.2 明写「抽一个共享常量(如 `DesignTokens.DIALOG_MASK_COLOR`)」;主会话派发词同一行也写了「补 `maskColor: '#8C000000'`,建议抽共享常量」。写完 1 分钟后(fixer-r1 v5 #23082/#23083)它才 grep `dimAmount` 并读 `BaseDialogFragment.kt@v2`/`AppLoadDialog.kt@v2` 做源码复核。
被改代码的来源: 纯新增(blame v2 changed:替换 0 行/新增 10 行)。前一版 `DesignTokens.ets@v1` 由 Base-6 公共组件库 base6-common v1(#3359,T+23:08)建。它没写这条,是因为派发词 §1 把 token 取值来源限定为「`resources/base/element/{color,float}.json` + `magic-numbers-report.md` 高频字面量」,并被 D0 纪律约束「不发明设计值,没有 Android 出处的数值不进表」;`dimAmount` 是 Android window 属性,不在 colors/dimens 资源表里,它的 v1 读取集里也没有任何弹窗基类源码。
生成时为什么没做好: 转换错在生成期的弹窗转换环——conv-fileconfirm / conv-vipbind / conv-refundreason / conv-renewrule / conv-custdialog v1 与 slice1-uibase v1 都**全文**读过 `BaseDialogFragment.kt@v2`(:47 `dimAmount = 0.55f` 就在文内),却没把这个 window 级属性映射成 ArkUI 的 `maskColor`,ArkUI 默认遮罩(≈0.20)又不报错,于是一路静默到视觉比对才暴露。
是否必要: 必要,像素实测 + 安卓源码默认值双证,且共享常量正是单里的处方;唯一瑕疵是注释里「每个 `new CustomDialogController(...)` 都必须带上本常量」写过头了。
证据(每条带坐标):
  1. diff `DesignTokens.ets@v2` — 只加 10 行 `DIALOG_MASK='#8C000000'` + 注释;blame v2 changed:替换/删除 0 行,新增 10 行 → 纯新增。
  2. `spec/fix/round-1/ui/_systemic/SYSTEMIC_dialog-mask-too-light.md@v1`(主会话·ff019d8a v70 #22214 建)§2/§3/§4/§5.2:三处实测 255→115 vs 255→204、根因未设 maskColor、建议抽共享常量。
  3. fixer-r1 v1 #22996 读该单全文;v4 #23055 写前读 `DesignTokens.ets@v1[142-196行]`(即 Palette 段),#23057 落 v2 → 改动直接由单驱动。
  4. fixer-r1 v5 #23082 `grep -rn dimAmount`、#23083 读 `BaseDialogFragment.kt@v2` 与 `AppLoadDialog.kt@v2`,时间 T+80:33,晚于 v2 落盘(T+80:32)→ 源码是事后复核,不是写值的原始依据。
  5. `BaseDialogFragment.kt@v2:47 protected open var dimAmount = 0.55f`(file content 38-53 行),该版下游读者含 conv-fileconfirm v1 / conv-vipbind v1 / conv-refundreason v1 / conv-renewrule v1 / conv-custdialog v1 / slice1-uibase v1,均标「全文」→ 生成期看得见却没转换。
  6. base6-common 派发词 §1 与 `DesignTokens.ets@v1:15-22 / :37`(取值三源 = 资源表 / `SettingBar.kt` / magic-numbers-report;「不发明设计值」)→ v1 写者的输入范围里根本没有弹窗蒙层。
  7. `DesignTokens.ets@v2:191` 写「每个 `new CustomDialogController(...)` 都必须显式带上本常量」,而 fixer-r1 收尾自述按 `AppLoadDialog.kt:93 override = 0.0f` 把 6 处 loading 弹窗改成 `Color.Transparent` → 注释与其自身最终处置不一致(注释写在读源码之前)。
无法确认的部分: ①「51 个控制器全补齐 / 24 文件 51 站点」无法在账本里逐点核验——实际打补丁走的是 `/tmp/patch_mask.py@v1`(fixer-r1 v5 #23133)与后续脚本,sessions 里这些弹窗文件全部标「脚本黑盒 / 方向不明」,不立版本;②`DIALOG_MASK` 是否被下游真正引用,只有 build-verify-r1 v6 对 `DesignTokens.ets@v2` 的「命中 1 行」这一条弱证据;③ 各弹窗页原始写者当时是否另有 spec 指示不设 maskColor,未查其派发词,无法确认。
置信: 中——修复动机、依据链、v1 写者的输入边界都有直接坐标可指;但「生成期漏做」定在弹窗转换环,依据的是「读了全文却没落 maskColor」这一反证(未逐个查 conv-* 的派发词),且落地面被脚本黑盒遮住。
```