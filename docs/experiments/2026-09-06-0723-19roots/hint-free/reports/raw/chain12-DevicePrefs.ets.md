```
文件: entry/src/main/ets/preferences/DevicePrefs.ets  修复方: 主会话 9b3105a2 的顶层 assistant(claude-opus-4-8,attributionSkill=arkts-visual-verify;非 ff019d8a 修复轮、非任何 subagent)  修改时间: 2026-07-25T02:59:57.729Z(uuid 911175cf-f40f-4771-b0f5-23f370ebbbfc,提交 c184680)
修复改了什么: 在 `// ---- OAID` 分隔注释前**纯新增** `getOrCreateAndroidId()`——复刻 `getOrCreateMarkId` 的「读时兜底」:读 `KEY_ANDROID_ID` 为空白则用 `util.generateRandomUUID(true)` 去连字符取前 16 位小写十六进制,生成即回写。配套改动:PreferenceKeys 新增 `KEY_ANDROID_ID`(5199)、F003Repository 导入 DevicePrefs 并把 `setPrivacyInfo(operators, '', '')` 的空串换成该值(5214/5221)。无一行旧代码被删。
修复的依据: 用户 `/arkts-visual-verify 请修复下当前的登录问题`(5146);assistant 定位到 `F003Repository.ets:385` 给 androidId 传空串 → 后端 `USER_INFO.ANDROID_ID` NOT NULL 违约 → 游客注册失败 → 无 token → 登录全链阻塞(5164);解锁凭据是 Base-3 的活体打靶实证——后端只校验非空+格式,16-hex 即被接受(5164 引 Base-3 结论)。
被改代码的来源: 纯新增,无被改代码。DevicePrefs.ets 原文由子 agent **abase5-preferences** 于 2026-07-24T10:42:33.170Z 一次性 Write(agent-abase5-preferences:110,uuid 0c1fe25c),依据是 `MMKVUtil.kt` 的键集(markId/oaid/sensitiveCity/huoshanAppId/installSource)——全文 0 次出现 androidId。它没写不是疏漏:ANDROID_ID 在 Android 侧来自 `Settings.Secure`,本就不是 MMKV 键,超出该 agent 的源文件范围;且它在交付报告里显式声明「`androidId`(D-010 🔴 阻塞项)仍无着落,本层**未臆造 UUID 冒充解决**」(agent-abase5:238,10:59:01)。空串调用点由 **aslice2-auth** 于 2026-07-24T12:09:13.743Z 写入(agent-aslice2-auth:193),注释写明「不在此处编造设备标识」,把 canonical 登记点指向 abase3 的 `P-BASE3-003`。
生成时为什么没做好: 卡在**编排器的派发纪律**这一环——主会话给各 slice 的 dispatch prompt 硬写了「🔴 D-010 `androidId` / D-011 `channel` 保持挂起,不得臆造取值」(主会话 3069/3095/3255/… 共 5 处),这条禁令在 Base-3 自己的活体打靶已证「16-hex 随便填后端就收」之后仍原样下发,证据没有回流去解冻这条冻结项。
是否必要: 必要——传空串是后端 NOT NULL 违约、游客注册 100% 失败,不改则登录链根本走不通;且改动自标 ⚠「测试解锁」、D-010 保持挂起,没有假装终局方案。
证据(每条带位置):
  1. 修复 Edit 本体:9b3105a2-85ec-4889-9786-b3c220f06754.jsonl:5203,`Edit DevicePrefs.ets`,old_string 仅一行 OAID 分隔注释 ⇒ 纯插入。
  2. 触发指令:同上:5146,`<command-args>请修复下当前的登录问题,修复完就返回即可;`(2026-07-25T02:54:51.105Z)。
  3. 根因判定:同上:5164(02:57:23)「`F003Repository.ets:385` 调 `setPrivacyInfo(operators, '', '')`… 后端 NOT NULL 列违约 → 游客注册失败 → 拿不到 token → **登录全链阻塞**」。
  4. 空串必失败的原始实证:agent-abase3-network-f9a03317492be8c4.jsonl:23(09:39:27)读到 spec「✗ `androidId` **不允许为空** —— `USER_INFO.ANDROID_ID` 是 NOT NULL 列,空串直接触发 `SQLIntegrityConstraintViolationException`」(2026-07-23 probe 实测)。
  5. 16-hex 可用的实证:agent-abase3-network:138 与 :268,`LIVE PROBE POST http://dev-api.whiap.cn/user/initUser`,body 内 `"androidId":"a1b2c3d4e5f60718"` → `HTTP 200`,`code:0`,返回 32 位 token、userId=28309661。
  6. 原文件作者与依据:agent-abase5-preferences-c92f24144fec6f9d.jsonl:110(2026-07-24T10:42:33.170Z)Write,文件头注释「源:`MMKVUtil.kt`(markId / oaid / sensitiveCity / huoshanAppId / installSource)」,全文无 androidId/ANDROID_ID。
  7. 「不臆造」纪律的两处落点:agent-abase3-network 写入 AppFormInfoManager.ets 的字段注释(经 agent-abase5:70 的 Read 回显可见,行 148-153)「D-010 头号阻塞项…本层只保留字段与传参路径,**不臆造 UUID 冒充解决**」;编排器派发词 9b3105a2 主会话:3069/3095/3255 等「🔴 **D-010 androidId / D-011 channel 保持挂起**,不得臆造取值」。
  8. 修复后验证与落库:主会话:5227-5232,编译 **BUILD SUCCESSFUL**,提交 `c184680 fix(D-010): 注入稳定 androidId 解锁游客注册链(测试解锁,待后端敲定最终方案)`。
无法确认的部分: ① 题面所说「DevicePrefs.ets 在修复轮(ff019d8a)被修改」与实录不符——ff019d8a 全会话+其 146 个 subagent 中,DevicePrefs 仅在 agent-afcfbf677a4e5864a.jsonl:55 的一次 `wc -l` 清单里出现(175 行),无任何 Write/Edit/sed 命中;真正的修改发生在 9b3105a2 会话尾部的交互式登录排障阶段。② 新值是否真被后端接受,只有编译 PASS,转录里没有改动后重跑 initUser 的活体验证。③ D-010 的最终方案(ODID/AAID 还是后端放开约束)在两轮转录中均未敲定。
置信: 高——修改点、上游作者、禁令原文、正反两侧 probe 证据都在原始 JSONL 里逐条命中且互相印证;唯一降级项是「修改属于哪一轮」与题面设定冲突,但该结论有全局 grep 支撑。
```