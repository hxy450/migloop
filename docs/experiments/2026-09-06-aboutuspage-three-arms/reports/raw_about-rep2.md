已追到底。以下是结论。

```
文件: entry/src/main/ets/pages/AboutUsPage.ets（+ 同案连改 entry/src/main/ets/viewmodels/F012ViewModel.ets）
修复版本/时间: 2026-07-26T20:56:12Z–20:56:55Z（修复轮 ff019d8a，round-1）
修复方: agent-a68daf720e780b4c2 = visual-fixer「fixer-r1」（meta.json: agentType=visual-fixer）

修复改了什么:
  应用名的「取值来源」从 bundleManager 的 appInfo.label 换成按名解析资源。
  ① F012ViewModel.ets（20:56:12，Bash python 补丁）：loadAppInfo() → loadAppInfo(context: common.UIAbilityContext | null)，
     应用名改走 context.resourceManager.getStringByNameSync('app_name')；并加防御——只有资源解析没拿到值
     且 label 不以 '$' 开头时才回落采信 label。版本号仍走 getBundleInfoForSelf().versionName，不变。
  ② AboutUsPage.ets（20:56:25，Edit）：aboutToAppear 改为 this.vm.loadAppInfo(this.abilityContext())，
     新增 private abilityContext() { getUIContext().getHostContext() as common.UIAbilityContext }。
  ③ AboutUsPage.ets（20:56:55，Edit）：补 import { common } from '@kit.AbilityKit'。
  症状：页面 App 图标下方原样渲染出字面量「$string:app_name」，应为「DeepAI全能PPT」。

被修代码的来源:
  首写 = 生成轮 agent-aconv-aboutus-02480823d9520ea1（customAgentType=a2h-activity-converter，model=opus），
  2026-07-24T07:31:58Z 的 Write AboutUsPage.ets，第 307 行 `this.appName = info.appInfo.label`，
  并在 120-121 行写下错误注释「鸿蒙侧等价物是 app.json5 的 label → 运行期经 bundleManager 读 appInfo.label 取真值」。
  搬运者 = agent-aslice6-risk-d4a26e5b9d8d7364（a2h-migration-worker），2026-07-24T14:42:49Z Write F012ViewModel.ets，
  把该行连同错误注释逐字搬进 VM（第 95/101 行），14:43–14:46 改 AboutUsPage 接 VM。搬运者未引入新错误。

定性: 漏读（该读没读）—— 目标侧一条 `cat AppScope/app.json5` 从未执行；上游 spec 措辞含糊是诱因

证据链:
  1. 2026-07-24T01:54:07Z 主会话 9b3105a2 行 1878（Stage 0，arkts-app-identity skill）：Bash 输出里赫然是
     `"label": "$string:app_name"`。01:54:19 的 assistant 文本自述「label/icon 已是引用，只改 version」，
     01:54:28 的 python 把 app_name="DeepAI全能PPT" 写进 AppScope/resources/base/element/string.json。
     → 真值与「label 是引用串」这一事实在编排者自己的上下文里，比 bug 早 5.5 小时，但从未回写进任何 spec 产物。
  2. spec/baseline/plans/resource-mapping.md:615（由 conv-aboutus 于 07:25:46 grep 到，行 61/62）：
     「appName ... 应写入 AppScope/app.json5 的 label 字段（**或**对应 string.json + app.json5 引用）」——
     两个方案并列、没说实际落地的是哪一个，也完全没提运行期怎么取。这是转换者唯一拿到的相关"规格"。
  3. conv-aboutus 全 123 行转录的工具调用清单（07:23:38–07:35:25，共 ~30 次）：Read/Bash 覆盖了 Android 侧
     AboutUsActivity.kt、activity_about_us.xml、SettingBar.kt、ContextConstant.kt、baseline md、view.xml，
     但**没有任何一次触碰 AppScope/app.json5 或 AppScope/resources/base/element/string.json**；
     07:25:48 的资源 grep 只查了 entry/src/main/resources/base/element/*.json（作用域漏掉 AppScope）。
  4. 它读到的 spec/baseline/ui/page_0031_AboutUsActivity.md（07:23:39，全文仅 2075 字符）通篇不含
     appName / app_name / label / 版本 任何字样 —— 「@string/appName 的鸿蒙等价物是什么」这条根本无人下发。
  5. 同轮反例：agent-abase3-network-f9a03317492be8c4 于 2026-07-24T09:51:27Z 执行 `cat AppScope/app.json5`，
     看到 `"label": "$string:app_name"`，两分钟后（09:53:45）写 AppFormInfoManager.ets 时用了
     `resourceManager.getStringSync(appInfo.labelId)` —— 同一问题在同一轮、同一仓里被正确解过一次，
     只是这条知识没有任何机制传给 2 小时前的 conv-aboutus。
  6. 检出：修复轮 agent-a2360912ac99796fb（general-purpose，name=vv-t2-A01，2026-07-26T17:42–18:23）
     跑 trip_2_logged_in_vip 双端截图+dump 比对，抓到节点 text="$string:app_name" bounds [385,1002][831,1063]，
     18:23:28 写出 spec/fix/round-1/feat/AboutUsActivity_01_app_name_unresolved.md（P0，similarity 0.88）。
  7. 修复者的关键动作：20:54:29 cat 该 finding；**20:55:14 一条 Bash 同时 `sed AppScope/app.json5` + `cat AppScope string.json`**
     —— 正是引入者从未做过的那一步；20:56:30 再 `grep -rn "appInfo.label" entry/src/main/ets/` 做同源自查
     （查出 F013Service.ets:1616 另有一处，判定为查别的 bundle 的埋点 payload，明确不动并记录）。

对比修复方: 修复方看了什么而引入者没看
  - AppScope/app.json5 的实际内容（label = "$string:app_name"）与 AppScope/resources/base/element/string.json
    的 app_name 真值 —— 引入者一次都没打开过这两个文件，纯靠 resource-mapping.md 的一句含糊描述倒推运行期 API。
  - Android 实测基线截图 + 鸿蒙 dump（android_trusted=true 的强 oracle）。引入者在 2026-07-24 时无设备回归，
    只有静态源码，`appInfo.label` 的返回形态无从证伪。
  - 全仓 `appInfo.label` 直方图。引入者从未横向对照仓内既有正确写法（AppFormInfoManager 的 labelId 解析）。

无法确认的部分:
  - 「bundleManager 原样回传引用串、不解析」这一 SDK 行为，转录里只有 dump/截图的经验证据，没有官方文档引用；
    修复方也只是断言。不影响结论（现象已双证）。
  - conv-aboutus 07:31 写文件前有一段 ~3 分钟无工具调用的思考（07:28:55→07:31:58），是否还看过别的东西无法从转录判断。
  - 修复后是否有 round-2 复测确认「DeepAI全能PPT」真的渲染出来了，本目录转录中未见（fixer 只写了"预期效果"）。
  - 生成轮的 closer/review 类 agent（abatch*/agroup*）为何未拦下这处，未逐个核（未在其转录中检索到针对该行的复核记录）。

置信: 高 —— 首写记录、错误注释、缺失的那条读取、含糊的 spec 行、同轮正确反例、检出与修复动作全部有带时间戳的具体调用可指回，链条无断点。
```

**工具使用小结（约 31 次调用，几乎全是 Bash）**：3 次目录/grep 定位锁定候选 agent，其余全部是 `python -c` 内联解析 JSONL——按行筛关键词后只反序列化命中行，再从 `message.content[].tool_use/tool_result` 与 `toolUseResult.file.content` 里取需要的片段，从不整文件 Read（主会话 13MB、子 agent 共 146 个）。最费力的一步是**从"谁写错的"往上追到"为什么会这么写"**：conv-aboutus 全程没提过 app.json5，只能反过来枚举它读过的每一个 spec 产物，逐个 grep `appName`，才在 resource-mapping.md 的一次 grep 结果里翻出那句二选一的措辞；随后再用「$string:app_name 在全部转录中的最早出现时间」把线索钉回主会话 Stage 0。