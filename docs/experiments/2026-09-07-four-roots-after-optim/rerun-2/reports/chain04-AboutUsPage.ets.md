```
文件: entry/src/main/ets/pages/AboutUsPage.ets  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v12-v13
修复改了什么: v12 把 `this.vm.loadAppInfo()` 改成 `this.vm.loadAppInfo(this.abilityContext())` 并新增私有 `abilityContext()`(取 getUIContext().getHostContext() 转 UIAbilityContext);v13 补 `import { common } from '@kit.AbilityKit'`。目的是让 VM 拿到 resourceManager 按名解析 app_name,而不再用 appInfo.label。
修复的依据: 派发词把 `AboutUsActivity_01_app_name_unresolved` 列为 P0(「F012ViewModel.ets:101 取 appInfo.label,而 AppScope/app.json5:8 的 label 本身是 $string:app_name,bundleManager 原样回传不解析」);fixer 现场读了该单全文(#25209@L240)并复核 F012ViewModel.ets@v1[60-120行] + AppScope/app.json5@v2[1-15行] + string.json(#25221@L250)。单据判据是安卓/鸿蒙实测截图对照(similarity 0.88,multimodal_severity high)。
被改代码的来源: 被替换的 2 行(v11:145-146 的注释 + `this.vm.loadAppInfo()`)由 slice6-risk(Slice 6 风控与内容合规 F012)写在 AboutUsPage.ets@v7(agent v14,#21598@L210);它同时写的 F012ViewModel.ets@v1:95/101 明写「`@string/appName` → `appInfo.label`(app.json5 的 label)」,依据是它读到的 spec/baseline/ui/page_0031_AboutUsActivity.md@v2 第 51 行(#21454@L70)。`abilityContext()` 与 import 是纯新增 —— v11 的写者按该 spec 认为 loadAppInfo 不需要 context。
生成时为什么没做好: spec 写错 —— conv-aboutus v4 写 page_0031@v2:51 时,把 resource-mapping.md@v1:615「应写入 app.json5 的 label」这条计划当成事实,断言 `appInfo.label`「已实装」,而它自己从未读过 AppScope/app.json5 的实际内容;slice6-risk 照此转写,是下游受害者。
是否必要: 必要,安卓基线截图显示应用名「DeepAI全能PPT」而鸿蒙侧渲染出字面量 `$string:app_name`,是实测可见的迁移缺陷。
证据(每条带坐标):
  1. diff AboutUsPage.ets@v12(fixer-r1 v17,#25233@L260)与 @v13(fixer-r1 v18,#25245@L270)= 传入 abilityContext + 补 @kit.AbilityKit import。
  2. blame AboutUsPage.ets@v12 changed:被替换 2 行,引入者 slice6-risk,引入于文件 v7;file 脊柱显示 v7 ← slice6-risk v14(#21598@L210)。
  3. F012ViewModel.ets@v1:95/101(slice6-risk v10,#21589@L200)= `| @string/appName | appInfo.label(app.json5 的 label) |` 与 `this.appName = info.appInfo.label`。
  4. spec/baseline/ui/page_0031_AboutUsActivity.md@v2:51「`bundleManager.getBundleInfoForSelf().appInfo.label`(已实装)」,首次出现即 v2,写者 conv-aboutus v4(#7019@L115);slice6-risk v1 读到该行(#21454@L70)。
  5. conv-aboutus ≤v4 搜 "app.json5" 只命中 resource-mapping.md@v1:152/615 的读(#6954@L62),无任何 AppScope/app.json5 的读记录;搜 "app_name" 同样只命中 resource-mapping。
  6. AppScope/app.json5@v2:8 实为 `"label": "$string:app_name"`,该版为「实录外修改」,读者 vv-t2-A01 v1(#24390@L184)——即出单方核实到的事实。
  7. 同一版窗口内 fixer 用 python heredoc 改了 F012ViewModel.ets(#25232@L258,输出 "ok F012ViewModel"),把 appName 改为经 resourceManager 按名解析 app_name,与本页传 context 的改动配套。
无法确认的部分: app.json5@v2 的 `label` 是谁写成 `$string:app_name` 的(标为「实录外修改」,无写者记录);修复后是否真的渲染出「DeepAI全能PPT」无实录证据(派发词明令不重编不复测);sessions 末尾 fixer-r1 v26 #25477@L506 有一次对本文件的「脚本字面量方向不明」调用,是否再改过本文件未确认(未展开)。
置信: 高 —— 修复方的读取集、被改行的引入者、以及错误 spec 行的写者与传播路径三跳都有账本上的边,唯一断点是 app.json5 的写者不在实录内。
```