```
文件: entry/src/main/ets/pages/AboutUsPage.ets  修复版本: v12+v13  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)
修复改了什么: v12 把 `this.vm.loadAppInfo()` 改成 `this.vm.loadAppInfo(this.abilityContext())` 并新增 `abilityContext()` 取宿主 UIAbilityContext(diff@v12);v13 补 `import { common } from '@kit.AbilityKit'`(diff@v13)。理由写在注释里:app.json5 的 label 是引用串 `$string:app_name`,bundleManager 原样回传,应用名须走 resourceManager 按名解析 app_name。
被修行的来源: slice6-risk@v7(blame AboutUsPage@v11 第145-146行 = 文件 v7 ← slice6-risk agent v14);新增的 `abilityContext()` 与 `common` import 属纯新增,无原作者。
定性: spec 写错(叠加漏读)
证据链(每条带引用):
  1. 被修的两行是 `// 对位 initView()…` + `this.vm.loadAppInfo()`,blame(AboutUsPage@v11) 判给 slice6-risk@v7,对应 agent slice6-risk v14(file 脊柱 v7 ← slice6-risk v14)。
  2. 真正的取值在 F012ViewModel.ets@v1:97-101(slice6-risk v10 创建):`loadAppInfo(): void { … this.appName = info.appInfo.label }`,页内那行只是无参调用点。
  3. slice6-risk v1 全文读 spec/baseline/ui/page_0031_AboutUsActivity.md@v2,stdout 对账"看见 51: `appName` | `bundleManager.getBundleInfoForSelf().appInfo.label`（已实装） | …鸿蒙侧等价物是 `app.json5` 的 `label`" —— 引入者是照 spec 这一行写的,VM 注释(F012ViewModel@v1:95)原样抄了这句映射表。
  4. 这一行不是外部基线给的:diff(page_0031_AboutUsActivity.md@v2) 显示"状态接口"整张表是 conv-aboutus v4 新增(v1 该处原文为"_未扫描到 LiveData / StateFlow / ViewModel_"),即写页的 agent 把自己的实现回填成 spec,再被下游当权威读走。
  5. slice6-risk v1-v14 的读取集里没有 AppScope/app.json5、没有 AppScope/resources/base/element/string.json(agent slice6-risk v14 时间线);它对 bundleManager 的核查只到 ApplicationInfo.d.ts 的 appDistributionType 段(action #14384),没看 label 的语义。
  6. 修复方在 fixer-r1 v17 读了 F012ViewModel.ets@v1[60-120行]、AppScope/app.json5@v2[1-15行]、AppScope/resources/base/element/string.json(#16924),外加修复单 `AboutUsActivity_01_app_name_unresolved`(#16916,派发词 P0 第 5 条已点名"F012ViewModel.ets:101 取 appInfo.label,而 AppScope/app.json5:8 的 label 本身是引用串")。
  7. 派发词侧无冲突指令:slice6-risk 的派发词只给了 feature-plan 336-375 行与 F012 feature spec 作先读清单,没有要求核对 app.json5/资源表,也没禁止 —— 属先读清单不含关键事实源。
对比修复方: 修复方读了 AppScope/app.json5@v2[1-15行] 与 AppScope/resources/base/element/string.json(fixer-r1 v17 #16924),引入者从头到尾没读过这两个文件(file(AppScope/app.json5) 的下游读者列表里无 slice6-risk / conv-aboutus);双方都读了 F012ViewModel@v1 与 AboutUsPage,差别只在"label 的事实源"这一处。
无法确认的部分: ① 账本里 F012ViewModel.ets 只有 v1,修复方对 VM 的改动是用 python heredoc 打的(action #16935,脚本落盘),未登记成新版本 —— 修好后的 `loadAppInfo(context)` 实现只能从脚本输入原文推断,VM 现行全文无法复原;② `appInfo.label` 是否真会把 `$string:app_name` 原样渲染出来,账本里只有修复单与修复方的断言,没有运行期/截图证据;③ conv-aboutus 写 spec v2 时 AppScope/app.json5 只有 @v1(外部输入、内容未知,v2 是 07-24T09:51 的实录外修改),故它当时能否查到 label 值,无法判定。
置信: 高,被修行的归属(blame@v11)、引入者当场看见的 spec 原句(slice6-risk v1 对账行 51)、以及双方读取集的唯一差异(app.json5/string.json)三条都是直证;唯一软处是 VM 侧改动走脚本、未登记版本。
```