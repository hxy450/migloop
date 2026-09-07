# 0723 aippt · WXEntryAbility.ets 返修链亲手调查

会话 SID = ff019d8a(修复期)/ 9b3105a2(生成期,前序会话)
目标文件 `entry/src/main/ets/wxapi/WXEntryAbility.ets` —— 链型 **created**(生成期未产出,修复期新建)

---

## 第一段:链报告

### 环 1 · 修复方落盘
**谁**:fixer-r1(visual-fixer,`agent-a68daf720e780b4c2`)v26 → 新建 `entry/src/main/ets/wxapi/WXEntryAbility.ets@v1`(#25535@L557,T+81:24);紧接 v28 在 `entry/src/main/module.json5@v5` 的 `abilities[]` 注册(#25542@L565,T+81:25,第 89-90 行 `"name": "WXEntryAbility"` / `"srcEntry": "./ets/wxapi/WXEntryAbility.ets"`)。
**凭什么**:两次读修复单 `spec/fix/round-1/feat/WXCallbackActivity_01_no_wxentry_callback_ability.md@v1`(#25506@L535、#25521@L548);配套读 `module.json5@v4`[1-60行 写前读]、`WxCallbackHandler.ets@v15`[225-275行]、`WxPayEntryHandler.ets@v2`[60-100行]、`EntryAbility.ets@v37`(#25524/#25528/#25532)。
**判定:传递**。写出来的 71 行与修复单 §5 的建议 1/2/4 逐条对得上 —— `onCreate`/`onNewWant` 双入口转交、分发后 `terminateSelf()`、以及「SDK 未入仓期间必须自关闭,避免透明回调 Ability 滞留前台」这条兜底纪律(修复单 §5.4 原话)。没有自创判断。

### 环 2 · 修复单的产出
**谁**:vv-static-B(general-purpose,`agent-afcfbf677a4e5864a`,「B系列静态验收」)v10 → `spec/fix/round-1/feat/WXCallbackActivity_01_no_wxentry_callback_ability.md@v1`(#28394@L175,T+77:58)。文本实际是它 v5 写的批量脚本 `…/scratchpad/gen_static.py@v1`(#28375@L161,T+77:53)里的字面量,脚本跑出 md。
**凭什么**(修复单 evidence 段 + 账本里的读):
- 读安卓 `pay/src/main/AndroidManifest.xml`(#28237@L85,T+77:44,与 `BaseWXPayEntryActivity.java`/`WXCallbackActivity.java` 同一次读)—— stdout 对账行显示它看见了 `:20 android:name="…BaseWXPayEntryActivity"`、`:27 android:name="${applicationId}.wxapi.WXPayEntryActivity"`、`:30 android:targetActivity="…BaseWXPayEntryActivity"`,即 **activity-alias → targetActivity 这层关系**。
- 读装配后的鸿蒙仓:`F003ViewModel.ets@v17` 第 351 行(#28324@L128)、`WxCallbackHandler.ets:253/257`、`module.json5:33`。
**判定:传递**(判断正确且有据)。附带一条工具缺口它自己记了:`spec_oracle: UNRESOLVED(inject_spec_oracle.sh 不存在于 .claude/skills/arkts-visual-verify/scripts/ 下)`,只能退回自取安卓锚点。

### 环 3 · 生成侧最后一次机会:被点名却没人建
**谁**:slice2-auth v4 → `F003ViewModel.ets@v1` 第 350 行写下「回调经 **WXEntryAbility** → `WxCallbackHandler.onResp` → 本 VM 的 wxAuthListener 回流」(#20107@L213,T+24:14;后经 v43 微调为第 349 行,#20224@L331)。
**凭什么**:读 `WxCallbackHandler.ets@v13` 第 230 行(#19998@L97,T+23:54)——「回调结束钩子:对应源 `Activity.finish()`——宿主微信入口 UIAbility(**WXEntryAbility**,SDK 门面)自行终止」。名字是从环 5 的注释里抄来的。
**判定:传递**。它照上游的措辞写,自己没有产出 Ability 的任务。
**同环的旁支**:group1-closer v1 在 T+24:36 读到 `F003ViewModel.ets@v16` 的这一行(#13077@L49),没有任何动作 —— 这是生成期最后一个看见「注释承诺了一个不存在的宿主」的角色。**判定:错(弱)** —— 有输入没用;但 closer 的职权边界写在系统提示里、不在转录里,不能确认它有权新建 Ability。

### 环 4 · 缺口被登记成了「SDK 待入仓」,但登记的不是这个缺口
**谁**:batch7-closer v27 → `spec/placeholder-registry.md@v15` 第 25 行登记 `P-S2-012`(#6269@L176,T+17:20),锚点 `WxCallbackHandler.ets:255`,范围写死为「微信登录 SDK 入仓:IWXAPI 创建 / registerApp(WX_APP_ID) / handleIntent 解析 want→resp」,kind=thirdparty-sdk,挂 decision-ledger **D-013**。
**判定:错**。占位的边界画在「SDK 解析」上,**宿主 Ability 注册(纯 ArkTS 接线)落在边界之外**:既没被产出,也没被登记为待办。否定证据 —— `search(q="WXEntry", file=placeholder-registry.md)`:该文件 **57 个版本的已知内容里从未出现 "WXEntry" 这个词**。147 条占位里没有一条对应它。也就是说,这个缺口在生成期是**无主**的,不是「已知待办」。

### 环 5 · 转换器落盘:把宿主判给了 SDK
**谁**:conv-wxcallback(a2h-activity-converter,`agent-aconv-wxcallback-3f5b8f543d8ac407`)v1 → `entry/src/main/ets/components/WxCallbackHandler.ets@v1`(#12506@L70,T+17:03)。该版第 7 行即写「微信 SDK(IWXAPI 创建/registerApp/handleIntent 解析 want→resp/**WXEntryAbility 注册**)华为侧…」、第 209 行「宿主微信入口 UIAbility(WXEntryAbility,**SDK 门面**)自行终止」。
**凭什么**:派发词(全文可见)+ `spec/baseline/ui/page_0037_WXCallbackActivity.md@v1`[写前读](#12439@L8)+ 安卓源 `WXCallbackActivity.java@v2`、`WXHandler.java@v2`、`BaseWXPayEntryActivity.java@v2`、`WXAuthListener/WXBaseResp/WXErrorCode/WXPayEvent/AccessTokenResponse.java@v2`(#12446–#12461)+ `placeholder-registry.md@v11`、`feature-plan.md@v2`、各类 pitfalls 参考。
**关键的否定证据**:它 **一次 AndroidManifest.xml 都没读**(v1 全部读取记录里没有任何 manifest)。它读到的安卓侧只有 java 类,看不到 `wxapi.WXEntryActivity` 这个由 manifest alias 声明的约定入口。
**判定:传递**。派发词把输出钉死为单文件、明令「不写共享文件」(所以它连 module.json5 都不能碰)、且直接告诉它 WXEntryActivity 注册属三方 SDK。它照做了。

### 环 6 · 派发词:**故障进入点**
**谁**:主会话·9b3105a2 v124 派发 conv-wxcallback(#1447@L2899,T+16:55)。派发词原文两处:
> 本页无布局(微信 SDK 回调入口 WXEntryActivity 模式,处理登录/分享回调)。你产出的不是 UI struct,而是一个【回调处理类 / handler 模块】
> 2. 微信 SDK 具体接入(IWXAPI/handleIntent/**WXEntryActivity 注册**)→ **华为侧无等价,属三方 SDK**:用 `// PLACEHOLDER:` 或 `// FWD-REF:`

外加【输出】只有一个 `entry/src/main/ets/components/WxCallbackHandler.ets`、【返回报告】要求 `is_no_ui=true`、结尾「不编译、不写共享文件」。
**凭什么/该凭什么**:同一个主会话在 T+0:01 跑过全模块 Activity 清点(#23@L66,`grep -oE 'android:name="[^"]*Activity"'` 逐模块),stdout 里 `--- pay ---` 段明明白白四行:
```
cn.sanfate.pub.loginpay.wechat.WXCallbackActivity
cn.sanfate.pub.loginpay.wechat.BaseWXPayEntryActivity
${applicationId}.wxapi.WXPayEntryActivity
${applicationId}.wxapi.WXEntryActivity
```
**判定:错**。手里有「`wxapi.WXEntryActivity` 是一个被声明的组件」这条输入,仍写下「华为侧无等价」。事实是有精确等价:`UIAbility` + `module.json5` 的 `abilities[]` 条目 —— 环 1 的修复方用 71 行纯 ArkTS、**零 SDK 依赖**就补齐了,反证了「无等价」是错判。这一句把一个「现在就能做的接线」错误地打包进了「等 SDK 入仓」的桶,后面所有环都是它的下游。

### 环 7 · 页面清单的枚举口径:结构性根(追到批量脚本,停)
**谁**:`spec/baseline/ui/page_0037_WXCallbackActivity.md@v1`,标注 `external · 批量生成(脚本跑出来的,同批 58 个)`,主会话·9b3105a2 v21(#347@L536,T+0:42)。
**内容**:第 7 行 `android_source_anchors: WXCallbackActivity: "pay/…/WXCallbackActivity.java"`(**只有 java 锚点,没有 manifest/alias**);第 17 行 `输出文件: entry/src/main/ets/components/WxCallbackHandler.ets`(输出契约在这里就被钉成单个 components 文件);第 39 行 `→ converter **跳过**本契约`。
**判定:缺**。页面清单是按「有 `.java/.kt` 源文件的类」枚举的,而 `${applicationId}.wxapi.WXEntryActivity` 是 manifest-only 的 activity-alias、没有源文件,于是**从来没成为一页**,也就从来没有任何 agent 被指派去产出它。
**否定证据**:`index(query="wxapi")` 全实录只有两个文件,都是修复期新建的 `wxapi/WXEntryAbility.ets`、`wxapi/WXPayEntryAbility.ets`;`index(query="WX", kind=spec)` 全部 spec 只有 `page_0037_WXCallbackActivity` 与 `page_0038_BaseWXPayEntryActivity` 两页 baseline + 两份 round-1 修复单,没有任何 wxapi 入口页。
**为什么停在这**:再往上是那次批量生成脚本的枚举规则,按规程「追到批量生成的脚本为止」。

---

**故障进入点:环 6**(主会话 v124 的派发词)。
理由:环 7 只是「没人被指派」(缺),还可能被下游纠正 —— 转换器手里有 `WXHandler.java`、有 `BaseWXPayEntryActivity.java`,完全有机会问「宿主在哪」。真正把口子焊死的是环 6 那句 **「WXEntryActivity 注册 → 华为侧无等价,属三方 SDK」**:它(a)与同一会话 16 小时前亲手打出的 manifest 清单矛盾,(b)把纯 ArkTS 接线错划进 SDK 阻塞桶,(c)配合「输出=单文件」「不写共享文件」两条,使转换器**在物理上也无法**补这半条链。环 4 是这一错判的机械后果:占位登记照抄了同一个边界,于是缺口连待办都没进。

**修复侧多看到的**(三样,生成侧一样都没有):
1. **安卓 manifest 的 alias 层**。vv-static-B 直接读 `pay/src/main/AndroidManifest.xml`(#28237),看到 `activity-alias` 的 `targetActivity` 指向,才能断定 `${applicationId}.wxapi.WXEntryActivity` 是**系统约定的落地入口**而非 SDK 内部实现。生成侧:conv-wxcallback 零 manifest 读取;主会话 #23 的 grep 只抓 `android:name=`,拿到名字却拿不到「它是谁的别名」。
2. **装配完成后的全仓视野**。修复单 §3 的核心判据是跨文件的「零调用点」:`handleWant/onResp` 全仓无真实调用点、`WxCallbackHandler` 的 7 处跨文件引用全在注入侧。这个 grep 只有在所有 slice 落盘后才做得出来 —— conv-wxcallback 在 T+17:03 写 handler 时,`F003ViewModel.ets` 还要 **7 小时后**(T+24:14,环 3)才出生。
3. **生成侧自己写下的承诺被当成契约来对账**。修复单 §2 明写「鸿蒙侧对等契约由 `F003ViewModel.ets:351` 自己写明」—— 环 3 那句注释,在生成期只是一句描述,到了修复期成了可验收的断言。

**无法确认**:
- 主会话写环 6 派发词时(T+16:55),#23(T+0:01)的清单是否还在上下文窗口里。账本只能证明「读过」,不能证明「当时看得见」。
- 修复单引的 `pay/src/main/AndroidManifest.xml:13` / `:38` 两行原文:#28237 的 stdout 对账只露出了 `:20/:27/:30`(WXPay 那一侧)。文件读过是确定的,13/38 两行的字面内容没在账本里露面。
- group1-closer(环 3 旁支)的职权:类型说明来自系统提示,不在转录里,判不出它是否有权新建 Ability / 改 `module.json5`。
- 环 6 那句「华为侧无等价」是主会话现写的,还是派发模板/技能定义里的固定话术。账本里派发词只有全文、没有来源分解 —— 这直接决定环 6 该判「错」还是「传递」,我按现有证据判「错」。
- 环 1 窗口(fixer-r1 v25→v26)里混着 MemberCenter / GuideDetails / F019 的大量读,因为那些改动走 python heredoc(脚本黑盒)不立版本。**具体哪几条读喂了 WXEntryAbility 那一笔写**,账本没分开;我是靠内容相关性挑的(#25506/#25521/#25524/#25528/#25532)。

---

## 第二段:工具体验日志

### 逐次调用

| # | 调用 | 返回 | 评价 |
|---|---|---|---|
| 1 | `guide` | 2777 字 | 有用。标签含义(▲旧版/写前读/脚本落盘/外部输入)后面全用上了;「没有起点的 search 不存在」这条规矩提前避免了瞎搜。 |
| 2 | `sessions path=WXEntryAbility.ets` | 1181 字 | 有用一半。链型 created + 修复方 + 时刻都对。但「依据」和「修复侧多看到的」两段列的是 MineFragment/MemberCenter 的 4 份 ALIGN 单,与本文件无关 —— **有误导**,详见下。 |
| 3 | `file WXEntryAbility.ets v=1 content=1 diff=1 readers=1` | 6482 字 | 有用但一半浪费:creation 版的 diff 和 content 是同一份内容,打了两遍。 |
| 4 | `agent fixer-r1 v=26 since=24` | 5943 字 | 有用,但信噪比差:v26 窗口里 ~70% 是 MemberCenter/GuideDetails/sips/heredoc,和这笔写无关。真正有用的是那 5 条读。 |
| 5 | `file WXCallbackActivity_01_…md v=1 content=1 readers=1` | 5797 字 | **最有用的一次**。修复单全文把 §2 期望 / §3 实际 / §4 缺口 / §5 建议 一次给全,环 1 的「传递」判定和环 2 的证据链都从这里出。 |
| 6 | `search q=WXEntryAbility file=WxCallbackHandler.ets` | 608 字 | 极有用,性价比最高的一次。「首次出现 v1 ← conv-wxcallback」一步把生成侧写者钉住,还顺手给了「SDK 门面」这句关键措辞。 |
| 7 | `agent conv-wxcallback v=1` | 5578 字 | **决定性**。派发词全文(含「华为侧无等价」「输出=单文件」「不写共享文件」)+ 全部读取(证明零 manifest 读取)。环 5/6 全靠它。 |
| 8 | `file page_0037_WXCallbackActivity.md v=1 content=1 readers=1` | 1841 字 | 有用。「批量生成(同批 58 个)」标记 + 第 17 行输出契约 + 第 39 行「converter 跳过本契约」,环 7 成立。 |
| 9 | `agent __main__:9b3105a2 v=124 since=123` | 410 字 | **没用**。窗口太窄,只剩一条「派发 conv-wxcallback」,零读取(读全归到更早版本了)。想知道「派发词凭什么这么写」,这个入口答不了。 |
| 10 | `search q=WXEntryActivity agent=__main__ v=124` | 823 字 | 很有用,救了第 9 次的场。一次拿到「主会话读过 manifest 清单」+「派发词原文两行」,环 6 的「错」判定成立。 |
| 11 | `action #23 --from="WXEntry"` | 头行报 1779 字 | **误导**。只打印了锚点之后的尾巴,但头行字数报的是全量,我以为被截断了。 |
| 12 | `action #23`(不带 --from) | 1779 字 | 有用。拿到完整 `--- pay ---` 四行清单。但这一次是第 11 次的字数显示不一致害我重打的,等于白费一次。 |
| 13 | `index query=wxapi` | 153 字 | 有用。极短的强否定证据:全实录 wxapi 目录只有修复期新建的两个文件。 |
| 14 | `index query=WX kind=spec` | 745 字 | 有用。证明 baseline 只有 page_0037/0038 两页,没有 wxapi 入口页 —— 环 7 的「缺」。 |
| 15 | `agent vv-static-B v=10 since=8` | 1108 字 | 半没用。窗口 v9–v10 只有两笔写、零读(读都在 v1–v8)。created 链的「凭什么」被窗口切掉了。 |
| 16 | `search q=WXEntryActivity agent=vv-static-B v=10` | 1082 字 | 有用。发现修复单文本是 `gen_static.py` 里的字面量(批量产出),但也暴露「读」侧零命中,让我一度以为锚点是凭空写的。 |
| 17 | `search q=activity-alias agent=vv-static-B v=10` | 1948 字 | 大半没用。命中的是 VideoPlay 横竖屏那条无关的 alias 讨论。 |
| 18 | `search q=AndroidManifest agent=vv-static-B v=10` | 4173 字 | 有用,但只用到第一条(#28237 的 3 行)。其余 4000 字是 WorksPage/FileUpload/VideoPlay 的噪声。 |
| 19 | `search q=WXEntryAbility file=module.json5` | 271 字 | 有用且精准。确认注册那一半也补上了(v5 ← fixer-r1 v28)。 |
| 20 | `search q=WXEntryAbility file=F003ViewModel.ets` | 821 字 | 有用。首次出现 v1 ← slice2-auth v4,外加两条「读者读到过」—— 环 3 与 group1-closer 旁支都来自这一条。 |
| 21 | `search q=WXEntryAbility agent=slice2-auth v=4` | 649 字 | 有用。一步定死名字是从 `WxCallbackHandler.ets@v13:230` 抄来的 → 环 3 判「传递」。(这次前有一次调用因模型分类器不可用失败,与工具无关,重试即过。) |
| 22 | `search q=WXEntry file=placeholder-registry.md` | 98 字 | **性价比最高的否定证据**:57 版全无此词。98 个字换来「缺口从未被登记」。 |
| 23 | `search q=P-S2-012 file=placeholder-registry.md` | 4070 字 | 有用但过量。真正要的是第 25 行那条登记的范围;附带 10 条「读者读到过」全没用。 |

合计 23 次调用,约 4.9 万字返回;真正进报告的大约三分之一。

### 卡住的地方

1. **「喂这一笔写的读是哪些」问不出来,只能问「喂这个版本的读是哪些」。** fixer-r1 v26 的窗口(#4)把 v25 之后的所有读全算进 v26,因为中间那些 MemberCenter/GuideDetails 的改动走 python heredoc,被判成「脚本黑盒」不立版本。结果一个版本吞了 20 多条无关读。我只能靠内容相关性人工挑出 5 条,这一步没有账本背书,写进了「无法确认」。
2. **想问「谁本该产出这个文件」,没有入口。** created 链的核心问题就是这个。我绕成三次否定查询拼:`index(query=wxapi)`(全实录无)+`index(query=WX, kind=spec)`(baseline 只有两页)+`search(q=WXEntry, file=placeholder-registry.md)`(占位登记无)。三次都是否定证据,拼起来才是「无人被指派」。
3. **想问「这个安卓文件被谁读过」,没有反查。** `pay/src/main/AndroidManifest.xml` 是池外输入,`file(readers=1)` 我不确定对安卓路径成不成立,只好一个 agent 一个 agent 地 `search(q=AndroidManifest, agent=…)`。生成侧那边我是靠「conv-wxcallback v1 的读取列表里没有 manifest」这个**间接**的零命中来断的 —— 如果它的读取多到被截断,这个判断就不成立了。
4. **`action` 的 `--from` 与头行字数不一致**(#11 vs #12)。头行报 1779 字,实际只打印了锚点后的十来行,我误判成截断,又原样重打一次。
5. **search 必须先猜到起点。** 找 P-S2-012 那次,是我先从修复方写的注释里捡到这个 P-ID 才敢查。如果那句注释没写 P-ID,这条线就断了 —— 「某个缺口有没有被登记成待办」不该依赖运气。
6. **`agent(…, since=)` 对 created 链天然不友好**(#15)。修复单的作者 vv-static-B,写单那一版窗口里零读取,证据全在 v1–v8。guide 其实提醒过「子 agent 整段给」,但我为省字数用了窗口,踩了一次。

### 多余的部分(返回了但一个字没用)

- `file(content=1, diff=1)` 在 creation 版上把同一份内容打两遍(#3,约 3000 字白给)。
- fixer-r1 v26 窗口里的 MemberCenter / GuideDetails / F019 / `sips` / 四条 heredoc 黑盒(#4,约 3500 字)。
- `search q=activity-alias` 命中的 VideoPlay 横竖屏那三条(#17,约 1500 字)。
- `search q=AndroidManifest` 里 WorksPage/FileUploadPage/PPTFilePage 那些命中(#18,约 3000 字)。
- `search q=P-S2-012` 的 10 条「读者读到过」(#23,约 3000 字)—— 我要的是「谁登记的、范围是什么」,不是「谁读到过」。
- guide 结尾的「结论要求:六类定性」与本次任务的三类判定(传递/错/缺)对不上,没用上。

### 缺的部分(想要而没有)

1. **写级(而非版本级)的读取归属**:「这一笔 Write 是由哪几条 Read 喂的」。有脚本黑盒写入的 agent,版本级归属会失真一个数量级。
2. **created 链专用反查**:输入一个路径或一个安卓类名,一次返回「baseline 页面清单里有没有 / 有没有任何派发词把它列为输出 / placeholder-registry 里有没有对应条目」。现在这三条否定证据要 3–5 次调用手工拼。
3. **池外输入(安卓源码)的读者反查**:`file(安卓绝对路径, readers=1)`。「生成侧从没读过这个 manifest」这种结论,现在只能靠间接的零命中推。
4. **一个概念名的跨会话传播时间线**:我做了 4 次 search 才拼出 `WXEntryAbility` 这个名字的传播链(conv-wxcallback@T+17:03 → slice2-auth@T+24:14 → group1-closer 读到@T+24:36 → vv-static-B@T+77:44 → fixer-r1@T+81:24)。这应该是一次调用的事。
5. **派发词的来源分解**:这句话是模型现写的,还是批量模板/技能定义里的固定话术?环 6 判「错」还是「传递」完全取决于此,而账本只给全文。
6. **`action` 输出按行号取片段**:#28237 的命中只给了前 3 行,我要 `:13/:38` 就没有了,`--max` 也调不出更多。摘要说「原文用 action 展开」,但 action 展开的也是被裁过的 stdout。

### 该改的三条(按重要性)

1. **读取归属做到「写」这一级,不要停在「版本」这一级。** 一个 agent 只要用 heredoc/脚本改文件,那些写不立版本,夹在中间的所有读就会被下一次真写版本全部吸走。本例 fixer-r1 v26 吞了 20 多条无关读,直接让归因窗口失真,我被迫把「哪几条读喂了这笔写」写进「无法确认」。

2. **`sessions` 的「依据 / 修复侧多看到的」要按被修文件挑证据,别按「第一笔修复前读了什么」挑。** 查 `WXEntryAbility.ets` 时它列出的是 MineFragment 版本更新、MemberCenter 轮播指示器颜色/布局/字号、WebView 返回图标这 4 份 ALIGN 单 —— 与本文件毫无关系;而真正的唯一依据 `WXCallbackActivity_01_no_wxentry_callback_ability.md` **根本不在列表里**。照这条线索走会追进完全错误的分支。我是靠第 4 次调用把 v26 的读取全列出来才捞回正确的修复单。这是本次唯一一处**主动误导**。

3. **给 created 链一个专用入口。** created 链的答案永远是同一组三问:baseline 页面清单里有没有这一页?有没有任何派发词把它列进【输出】?placeholder-registry 里有没有它的待办条目?本例三问全否,结论就是「无人被指派、也没登记成待办」。现在这个结论要 `index` 两次 + `search` 两次 + 读派发词全文才拼得出,而且每一步都得先猜对关键词。
