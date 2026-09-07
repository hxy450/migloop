```
文件: entry/src/main/ets/pages/AboutUsPage.ets  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v12–v13(fixer-r1 v17 #23262 / v18 #23274,T+80:53)
修复改了什么: 把 `this.vm.loadAppInfo()` 改成 `this.vm.loadAppInfo(this.abilityContext())`,并新增私有方法 `abilityContext()`(getUIContext().getHostContext() → UIAbilityContext)与 `import { common } from '@kit.AbilityKit'`;配套把 VM 的取名方式从 `appInfo.label` 改成 resourceManager 按名解析 `app_name`。
修复的依据: 派发词 P0 第 5 条 + 单 spec/fix/round-1/feat/AboutUsActivity_01_app_name_unresolved.md@v1;fixer-r1 v17 自查了 AppScope/app.json5@v2[1-15行] 与 AppScope/resources/base/element/string.json(#23250),确认 label 值本身是引用串 `$string:app_name`,bundleManager 原样回传会把引用串渲染到页面。
被改代码的来源: 被替换的 2 行(v11:145-146 注释 + 无参调用)由 slice6-risk(agent-aslice6-risk-d4a26e5b9d8d7364)在 agent v14 写 AboutUsPage@v7 时接线;其真正病灶在它 v10 写的 F012ViewModel.ets@v1(#19882)里 `loadAppInfo()` 取 `appInfo.label`,依据是 spec/baseline/ui/page_0031_AboutUsActivity.md@v3:51 的状态接口表(#19748 grep 到)。新增的 10 行属纯新增,v11 写者没写是因为当时 VM 不需要 context。
生成时为什么没做好: 卡在转换环节——conv-aboutus v1 把派发词只授权用于 versionName 的 `getBundleInfoForSelf` 外推到应用名(未读 AppScope/app.json5),又在 v4 把该结论回填进 baseline spec page_0031@v3:51 标成「已实装」,slice6-risk 照 spec 原样搬进 VM,错误被 spec 回填放大一次。
是否必要: 必要 —— 缺陷真实(label 是引用串),且 VM 新签名要外部喂 UIAbilityContext,页面不改就拿不到 resourceManager;传 context 也正是本仓既有惯例(AppFormInfoManager.ets@v9:90)。
证据(每条带坐标):
  1. diff AboutUsPage.ets@v12 与 @v13:调用点加参 + 新增 abilityContext() 与 common 导入(fixer-r1 v17 #23262 / v18 #23274)。
  2. blame AboutUsPage.ets@v12 changed=True:替换 v11 的 2 行,引入者 slice6-risk@since_v7;新增 10 行。
  3. spec/fix/round-1/feat/AboutUsActivity_01_app_name_unresolved.md@v1 = 外部输入 T+78:19,fixer-r1 v16 读过(#23240);派发词 P0-5 直指「F012ViewModel.ets:101 取 appInfo.label,而 AppScope/app.json5:8 的 label 是 $string:app_name」。
  4. F012ViewModel.ets@v1 写者脊柱:v1 ← slice6-risk v10(#19882);fixer-r1 v17 用 python heredoc 就地改写它(#23261),把注释与实现改成 `resourceManager.getStringByNameSync('app_name')` 并加 context 形参。
  5. spec/baseline/ui/page_0031_AboutUsActivity.md@v3:51 原文(action #19748):「appName ← bundleManager.getBundleInfoForSelf().appInfo.label(已实装)」;该 v3 的写者正是 conv-aboutus v4(#5993),即自己实现后回填自己的结论。
  6. conv-aboutus 派发词只写「版本号读取:鸿蒙用 bundleManager.getBundleInfoForSelf 取 versionName」,收尾却称「版本号与应用名走 getBundleInfoForSelf 真实读取」;其 v1 读取集(#5865–#5973)中无 AppScope/app.json5。
  7. 同仓正确取法早已存在:AppFormInfoManager.ets@v9:88-90 `labelId → context.resourceManager.getStringSync(labelId)`;fixer-r1 v18 #23264 grep 到它与 F006Repository.ets:66 后才定型。
无法确认的部分: ① F012ViewModel 的修补是脚本黑盒(#23261),账本未立新版本,新签名的形参名/是否可选只能从 #23261 输入原文与 #23264 的 grep 推断;② slice6-risk 读 AppFormInfoManager@v7 时 labelId 那几行是否已存在——记录到的命中只有第 60、82 行(#19701/#19864),它是否"该读没读"到 88 行无法确认;③ page_0031@v2 是「实录外修改」、v1 内容未知,状态表最初由谁写成什么无法确认;④ 另有 fixer-r1 v26 #23492 用脚本改过 AboutUsPage.ets:242 的返回图标尺寸(方向不明调用,已确认是写),不在 v12/v13 这条链内,账本未立版本。
置信: 高 —— 修复内容、被改行归属、上游 spec 原文与 converter 的读取集四处坐标互相咬合;仅脚本落盘的 VM 新签名细节靠原文推断。
```