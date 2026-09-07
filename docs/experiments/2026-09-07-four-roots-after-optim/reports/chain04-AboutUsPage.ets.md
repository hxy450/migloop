```
文件: entry/src/main/ets/pages/AboutUsPage.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2 / fixer-r1)  修复版本: v12–v13(fixer-r1 v17、v18 @T+80:53–80:54)
修复改了什么: 把 `this.vm.loadAppInfo()` 改成 `this.vm.loadAppInfo(this.abilityContext())`，新增私有方法 `abilityContext()`（`getUIContext().getHostContext()` 取 UIAbilityContext）与 `import { common } from '@kit.AbilityKit'`——为同步改造的 F012ViewModel 供上 resourceManager 载体；另在 T+81:19(fixer-r1 v26,#25477)用脚本把本页标题栏返回图标 24x24 改为 12x19vp（该次未在账本立版本）。
修复的依据: 单 `spec/fix/round-1/feat/AboutUsActivity_01_app_name_unresolved.md@v1`（P0，android_trusted=true 的双端截图/dump 强 oracle：鸿蒙侧渲染出字面量 `$string:app_name`），fixer 在 #25209 读到全文；派发词也点名了这条。
被改代码的来源: 被替换的 2 行由 slice6-risk(agent-aslice6-risk-d4a26e5b9d8d7364) 在 AboutUsPage.ets@v7(它的 v14, #21598) 写下，依据是 `spec/baseline/ui/page_0031_AboutUsActivity.md@v2:51`「appName = bundleManager.getBundleInfoForSelf().appInfo.label（已实装）」与 AboutUsPage.ets@v3:121 的同款注释；新增的 10 行属纯新增——v11 写者(同一个 slice6-risk)手里那份 spec 认定 label 就是真值，不需要 context，故不会去写 `abilityContext()`。
生成时为什么没做好: spec 写错——conv-aboutus 只读了 `resource-mapping.md@v1:615`（「appName 应写入 AppScope/app.json5 的 label 字段」）就把「运行期经 bundleManager 读 appInfo.label 取真值」当结论固化进 baseline spec 并标「已实装」，全程没读过 `AppScope/app.json5` 本体，下游 slice6-risk 照抄这条 spec 实现。
是否必要: 必要——F012ViewModel 的 `loadAppInfo` 已改为 `loadAppInfo(context: common.UIAbilityContext | null)`(#25232)，调用方不传参即缺参、应用名恒为空。
证据(每条带坐标):
  1. diff(AboutUsPage.ets@v12) / @v13：改调用为 `loadAppInfo(this.abilityContext())` + 新增 `abilityContext()` + `import { common }`；blame(@v12, changed) 显示只替换 v11 的 145–146 两行，owner=slice6-risk@v7。
  2. fixer-r1 v17 的读取集(#25221)：`F012ViewModel.ets@v1[60-120行]`、`AppScope/app.json5@v2[1-15行]`、`string.json@v1`——三方对账后才动手；#25232 的 python heredoc 把 `this.appName = info.appInfo.label` 换成 `context.resourceManager.getStringByNameSync('app_name')` 并加 `startsWith('$')` 兜底。
  3. `spec/baseline/ui/page_0031_AboutUsActivity.md@v2:51` ← conv-aboutus v4(#7019) 写入；slice6-risk v1 在 #21454 读到并命中该行——这是错误处方进入实现的那一跳。
  4. search(q="app.json5", agent=conv-aboutus, ≤v4)：只命中 `resource-mapping.md@v1:152/615` 一处读，从未读 `AppScope/app.json5` 本体——「该读没读」的直接否定证据。
  5. search(q="app_name", agent=slice6-risk, ≤v14) 零命中——写 F012ViewModel.ets@v1(#21589) 与 AboutUsPage.ets@v7 之前，它没见过 `app_name` 这个真值来源。
  6. `AppScope/app.json5@v2:8` `"label": "$string:app_name"` 标为**实录外修改**（无记录在案的写者）；该行第一次被人读到已是 vv-t2-A01 v1 @T+78:02(#24390)，即生成期无人核对过它。
  7. fixer-r1 #25235 的 grep：`AppFormInfoManager.ets:88` 早已用 `resourceManager.getStringSync(appInfo.labelId)` 的正确取法——同仓存在正确先例，这条错并非 SDK 知识缺失，是 spec 与核实环节的问题。
无法确认的部分: 谁、在什么依据下把 `AppScope/app.json5` 的 label 写成引用串 `$string:app_name`（v2 记为实录外修改，无写者记录）；`resource-mapping.md@v1` 内容无法复原（stage0-resources v25 脚本落盘），第 615 行括号后是否写明「label 用引用串」只能看到截断片段；`abilityContext()` 所称「与本仓其它页同惯例」只见 fixer 读过 MineComponent.ets@v30(#25228)，未逐页核对。
置信: 高——修复动作、依据单、被改行归属、上游 spec 那一跳都有工具坐标闭环;仅 app.json5 引用串的引入者与 resource-mapping 原文两处缺记录，且不影响定性。
```