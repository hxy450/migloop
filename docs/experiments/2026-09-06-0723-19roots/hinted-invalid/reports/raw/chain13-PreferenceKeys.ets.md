```
文件: entry/src/main/ets/preferences/PreferenceKeys.ets  修复方: 主会话(编排/直接写盘) · arkts-visual-verify(9b3105a2-85ec-4889-9786-b3c220f06754)  修改时间: 2026-07-25T02:59:41.615Z
修复改了什么: 纯新增——在 KEY_MARK_ID 与 KEY_OAID 之间插入 `KEY_ANDROID_ID = 'android_id'` 及一段注释,声明它是鸿蒙侧自造的稳定设备标识,用来填后端 NOT NULL 的 `USER_INFO.ANDROID_ID`,并自我标注为「测试解锁,最终方案待后端敲定」。没有删改任何既有键。
修复的依据: 用户在 02:54:51 下达 `/arkts-visual-verify 请修复下当前的登录问题`;修复方定位到 `F003Repository.ets:385` 的 `setPrivacyInfo(operators, '', '')` 第二参传空串 → 后端 NOT NULL 列违约 → 游客注册失败 → 拿不到 token → 登录全链断(5164 行);并援引 Base-3 活体打靶「后端接受合法格式的 androidId」,于是复用 `DevicePrefs.getOrCreateMarkId()` 的持久化模式新造一个稳定 16-hex 值,新键是这套机制的落点。
被改代码的来源: 该位置原为空白(纯新增)。前一版整文件由生成轮子 agent **base5-preferences**(`a2h-migration-worker`, opus)在 2026-07-24T10:38:49 一次 Write 产出,依据是任务书指定的权威输入 `spec/baseline/feature-base.md` §5(20+ 键)+ 5 处 Android 源码常量类,文件头自述「MMKV 键名的唯一事实源,键名逐字复刻源码」。它没写 androidId 有两个原因:一是 Android 侧 ANDROID_ID 来自 `Settings.Secure` 运行时读取,**根本不是 MMKV 键**,按该文件的建键规则无从落地;二是它已知 D-010 并**刻意拒绝**——handoff 原话「`androidId`(D-010 🔴 阻塞项)仍无着落,本层**未臆造 UUID 冒充解决**」。
生成时为什么没做好: 编排层在 Base-3 任务书里把 D-010 写成硬政策「不要臆造一个 UUID 就当解决了」并推迟到 F003 联调,而 Base-3 自己的 live probe 同一小时内已用 16-hex 假值注册成功——政策与实证在同一个 agent 内部没有被回收对账,下游 Base-5/F003 只继承了政策,于是留下空串一路带到运行期。
是否必要: 必要——它是登录链的真实阻塞点,且是最小改动;唯一可议的是把一个无 Android 对应物的键放进自称「逐字复刻源码」的文件里,与该文件的建键规则不自洽(修复方已就地标注为临时方案)。
证据(每条带位置):
  1. 修改本体:`9b3105a2-*.jsonl:5199`(uuid c6cb4725-4c53-41d0-9f42-9f4b0f99b07a,2026-07-25T02:59:41.615Z,`attributionSkill:"arkts-visual-verify"`,`caller:{"type":"direct"}`)——Edit 的 structuredPatch 显示 oldStart 124 处 +9 行,纯插入。
  2. 触发指令:`9b3105a2-*.jsonl:5146`(2026-07-25T02:54:51.105Z)`/arkts-visual-verify 请修复下当前的登录问题,修复完就返回即可`。
  3. 诊断链:`9b3105a2-*.jsonl:5164`(02:57:23)「D-011 channel 默认已是 2301101 不阻塞;D-010 androidId `F003Repository.ets:385` 传空串 → NOT NULL 违约 → 登录全链阻塞」;`:5169`(02:58:27)决定复用 `DevicePrefs.getOrCreateMarkId()` 模式。
  4. 原作者与依据:`subagents/agent-abase5-preferences-c92f24144fec6f9d.jsonl:93`(2026-07-24T10:38:49.479Z)Write 全文,头部「键名值逐字复刻源码…按 owner 归并(feature-base.md §5)」;任务书见同文件 `:1`(10:28:30)「输入来源:feature-base.md §5(**权威**)…键名与源码逐字相同」。
  5. 刻意不写的自述:`agent-abase5-...jsonl:238`(10:59:01)handoff「`androidId`(D-010 🔴 阻塞项)仍无着落,本层**未臆造 UUID 冒充解决**,取值方案须与后端敲定」;其认知来自读到 Base-3 产出的 `AppFormInfoManager.ets` 注释(同文件 `:70`,10:32:27)。
  6. 政策源头:`subagents/agent-abase3-network-f9a03317492be8c4.jsonl:1`(2026-07-24T09:39:04)编排层任务书「D-010…**照常留字段与传参路径**,取值标 `// FWD-REF` 待 F003 联调定(不要臆造一个 UUID 就当解决了——那会让问题在联调时才暴露)」;Base-3 据此写下 `P-BASE3-003` 注释(同文件 `:169`,09:53:45)。
  7. 反证同时存在:`agent-abase3-...jsonl:132/135/138`(09:46:15–09:46:41)——签名对账与 `LIVE PROBE POST http://dev-api.whiap.cn/user/initUser` 的 body 里 `"androidId":"a1b2c3d4e5f60718"`(自造 16-hex),结果 `HTTP 200 / code:0` 注册成功。修复方一年后引用的正是这条。
  8. 配套与验证:`9b3105a2-*.jsonl:5203` 新增 `DevicePrefs.getOrCreateAndroidId()`、`:5214/:5221` 接线 `F003Repository.collectPrivacyInfo`(被替换的注释原文「不在此处编造设备标识」,同属生成轮遗留)、`:5230` BUILD SUCCESSFUL、`:5231` 提交 `c184680 fix(D-010): 注入稳定 androidId 解锁游客注册链`。
无法确认的部分: (a) 修复方注释里「后端只校验非空 + 格式合法(16 位十六进制即可)」的**格式**结论过度概括——Base-3 probe 只验证过 `a1b2c3d4e5f60718` 一个值成功、空串失败,没做过格式变体对照实验;(b) D-010 编号最初在哪份 spec/决策表登记(本目录转录里只见引用,不见其定义处);(c) 改完后是否真在设备/模拟器上跑通了完整登录——转录只见编译通过与提交,以及 `:5238` 修复方自述「已修复」,未见端到端登录成功的实测输出。
置信: 高——修改事件、触发指令、原文件的 Write 事件、原作者刻意不写的自述、以及政策与反证的双方原文都在转录里直接可读,时间线闭合;仅上面 3 点属外围细节。
```