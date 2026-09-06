已追到底。核心事实链完整。

```
文件: entry/src/main/ets/pages/AboutUsPage.ets
修复版本/时间: 2026-07-26T20:56:25.321Z 与 20:56:55.242Z(两次 Edit)
修复方: agent-a68daf720e780b4c2 (subagent_type=visual-fixer, name "fixer-r1"，由主会话 ff019d8a 于 20:33:31 派发，任务=修 spec/fix/round-1 的 51 条 finding)

修复改了什么:
  ① aboutToAppear(): `this.vm.loadAppInfo()` → `this.vm.loadAppInfo(this.abilityContext())`，
     并新增私有 `abilityContext(): common.UIAbilityContext | null`
     (走 `getUIContext().getHostContext()`，抄 MineComponent.ets:853 的同仓惯例)。
  ② 补 `import { common } from '@kit.AbilityKit'`。
  ③ 同一 agent 在 20:56:12 用 Bash/python 补丁改了配套的 viewmodels/F012ViewModel.ets：
     `this.appName = info.appInfo.label` → `context.resourceManager.getStringByNameSync('app_name')`，
     并加 `!label.startsWith('$')` 兜底守卫。
  本质: 应用名的事实源从 bundleManager 的 appInfo.label 换成 resourceManager 按名解析。
  真正的 bug 是 AppScope/app.json5 的 `"label": "$string:app_name"` 本身就是引用串，
  bundleManager 原样回传 → 界面上把 `$string:app_name` 当文案渲染出来了。

被修代码的来源: agent-aconv-aboutus-02480823d9520ea1，2026-07-24T07:31:58.920Z 的首次 Write
  (AboutUsPage.ets 全文 25900 字符)。该版本里就写着
  `this.appName = info.appInfo.label`，配注释「鸿蒙侧等价物是 app.json5 的 label →
  运行期经 bundleManager 读 appInfo.label 取真值」。
  2026-07-24T14:42:49 agent-aslice6-risk-d4a26e5b9d8d7364 把它原样搬进新建的 F012ViewModel.ets，
  再于 14:43–14:46 把页面改成委托 VM —— 缺陷换了个文件存活。

定性: 漏读(该读没读)
```

**证据链**

1. **缺陷在真机上的形态** — `agent-a2360912ac99796fb`(visual-verify)，2026-07-26T18:05:30，Bash 抓的设备 UI 树逐字返回 `['关于我们', '$string:app_name', 'V1.0.6', '用户协议', ...]`。同 agent 18:22:50 Read 出 finding `spec/fix/round-1/feat/AboutUsActivity_01_app_name_unresolved.md`(severity P0, is_migration_bug=true, android_anchor=`activity_about_us.xml:39-45 about_us_tv_name android:text=@string/appName`)。

2. **引入点** — `agent-aconv-aboutus`，07-24T07:31:58 Write，`loadAppInfo()` 内 `this.appName = info.appInfo.label`。

3. **关键漏读** — 全库扫 `AppScope/app.json5` + `AppScope/.../string.json` 的访问记录：aconv-aboutus 与 aslice6-risk **一次都没打开过**。aconv-aboutus 在 07:25:34 只 grep 了仓内 `bundleManager`(当时仅 1 条 H5PayDialog 的注释命中，无先例可抄)，然后在 07:31 写下「app.json5 的 label」这句断言 —— 断言的对象文件从未被读。决定答案的那一行(`"label": "$string:app_name"`)就在里面。

4. **同一映射，读了的人写对了** — `agent-abase3-network-f9a03317492be8c4` 于 09:51:27 跑 `cat AppScope/app.json5`，结果里明摆着 `"label": "$string:app_name"`；2 分钟后 09:53:45 写 `network/AppFormInfoManager.ets`，对**同一个** Android API(`ContextConstant.getAppName()` = PackageManager label)给出正确映射 `resourceManager.getStringSync(appInfo.labelId)`(:58 注释 / :88-90 代码)。正确答案 07-24 上午就在仓里，只是在另一个 agent、另一个文件。

5. **错误被"升格"成 spec** — aconv-aboutus 在 07:33:55 Edit `spec/baseline/ui/page_0031_AboutUsActivity.md`。它 07:23:39 读到的原文「状态接口」段是**空的**(`_未扫描到 LiveData / StateFlow / ViewModel_`)；它把自己的实现回填成权威表格：`| appName | string | bundleManager...appInfo.label(已实装) | ... 鸿蒙侧等价物是 app.json5 的 label |`。**spec 不是上游，是这次转换的下游产物。**

6. **回填的 spec 反过来固化了缺陷** — `agent-aslice6-risk` 14:21:25 Read 了带 bug 的 AboutUsPage.ets，14:23:58 grep 了上面那张回填表，14:42:49 写出的 F012ViewModel.ets 抬头就标「对齐 `spec/baseline/ui/page_0031_AboutUsActivity.md` 状态接口表」。它 14:28:14 确实 grep 过 `AppFormInfoManager.ets`，但查询是 `"static \|export class"` —— 只拿回方法名清单，正确写法所在的 :88 行擦肩而过。它 14:31:50 还读了 SDK 的 `ApplicationInfo.d.ts`，但落在 `appDistributionType` 段，没落在 label。

7. **闸口没拦住** — `agent-abatch11-closer` 07:40:50 Read AboutUsPage.ets 时带了 `limit: 150`，只覆盖到那句自我辩护的声明注释，`info.appInfo.label` 的实际调用点在文件尾部，不在读取窗口内。全生成轮 40 条 `appInfo.label` 记录里，没有任何一条是对它提出质疑。

**对比修复方: 修复方看了什么而引入者没看**

fixer 在 20:55:14 一条 Bash 里同时 `sed -n '1,15p' AppScope/app.json5` + `cat AppScope/resources/base/element/string.json` —— 正是 converter 跳过的那次读取，一眼看到 `label: "$string:app_name"` 与 `app_name: "DeepAI全能PPT"`。此外它有两样引入者没有的东西:(a) 真机证据，UI 树里那串 `$string:app_name` 把「该不该信 label」变成了事实问题;(b) 20:56:30 全仓 `grep -rn "appInfo.label"`,拿到 `AppFormInfoManager.ets:58/88` 这个现成的正确先例,并顺手判定 `F013Service.ets:1616` 查**他人**包名时用 label 是合理的、不改。

**无法确认的部分**

- 修完后是否有 round-2 视觉复测确认 AboutUsActivity 已修好:我看到 21:45 主会话写了 `spec/visual-verify/report.md`,但没去核对其中是否重测了本页,也没看到本次修改的编译结果。
- `page_0031_AboutUsActivity.md` 的「状态接口」段最初为空,是上游 UI 基线生成器的固有缺口还是本页特例 —— 未追到生成该 md 的环节。
- aslice6 为何用 `static |export class` 而不是 `appName` 去 grep AppFormInfoManager,转录里无从判断意图。

**置信: 高** —— 首写、spec 回填、二次搬运、修复四个动作各有确切时间戳与工具调用原文,且存在同轮同映射「读了 app.json5 就写对」的对照组(abase3-network),漏读与错误的因果不是推测。

---

约 29 次工具调用,几乎全是 Bash:先 `grep -rlo` 按文件统计 `AboutUsPage` 命中做定位,再写三个小 python 脚本复用 —— 扫全库 Write/Edit 的 file_path 定位改动点、按行号导出 tool_use/tool_result 原文、打印单 agent 工具调用时间线。最费力的是判断 spec 与代码谁先谁后:`page_0031` 那张表看着像上游指令,只有把 converter 的 Read(07:23:39,该段为空)和它自己的 Edit(07:33:55)两个时间戳并排,才认定 spec 是它的回填、而非它的依据 —— 这一步直接决定了定性是「spec 写错」还是「漏读」。