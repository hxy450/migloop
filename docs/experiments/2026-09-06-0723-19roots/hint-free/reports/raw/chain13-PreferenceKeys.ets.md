```
文件: entry/src/main/ets/preferences/PreferenceKeys.ets  修复方: 主会话 9b3105a2 顶层 orchestrator(session 9b3105a2-85ec-4889-9786-b3c220f06754,无 agentId,非 sidechain)  修改时间: 2026-07-25T02:59:41.615Z(uuid c6cb4725-4c53-41d0-9f42-9f4b0f99b07a),提交 c184680

修复改了什么: 在 KEY_MARK_ID 与 KEY_OAID 之间纯新增一个键 `static readonly KEY_ANDROID_ID: string = 'android_id'`(带 D-010 注释,标注"测试解锁,最终方案待联调")。同一批还改了 DevicePrefs.getOrCreateAndroidId() 和 F003Repository.collectPrivacyInfo(),把原来的 setPrivacyInfo(operators, '', '') 换成注入实值。

修复的依据: 用户在 5146 行下达 `/arkts-visual-verify 请修复下当前的登录问题`;orchestrator 定位到 F003Repository.ets:385 传空串 androidId → 后端 USER_INFO.ANDROID_ID(NOT NULL)违约 → 游客注册失败 → 拿不到 token(9b3105a2:5164)。技术依据是 Base-3 自己的活体打靶:用伪造值 androidId="a1b2c3d4e5f60718" 真发 POST http://dev-api.whiap.cn/user/initUser,HTTP 200 / code=0,拿到 32 位 token 与 userId=28309661 —— 证明后端只校验非空+16-hex 格式(agent-abase3-network:138/268)。

被改代码的来源: 纯新增。前一版由子 agent base5-preferences(agentType a2h-migration-worker, model opus)在 2026-07-24T10:38:49.479Z 一次性 Write 出整个文件,文件头自定的口径是"MMKV 键名的唯一事实源,键名值逐字复刻源码,任何情况下都不得改写",键集严格来自 Android 的 MMKVUtil.kt / UserData.kt / MMKVKeyExt.kt / AppContant.kt。Android 侧 ANDROID_ID 是运行时读 Settings.Secure、根本不是 MMKV 键,所以按"逐字复刻源码"的口径 Base-5 不写它是正确的;这个键是鸿蒙侧独有的新增物。

生成时为什么没做好: 卡在 forward-ref 转派这一环 —— Base-3 把 androidId 登记成 P-BASE3-003 / D-010"后端阻塞项",明文写"不臆造 UUID 冒充解决",resolve_by=Slice 2 Step 3c;而 orchestrator 派给 slice2-auth 的任务书又明令"保持挂起、不要臆造取值……你不要擅自定",于是接盘人被禁止解决,占位一路漂到修复轮才由 orchestrator 自己拍板。

是否必要: 必要 —— 空串 androidId 会让游客注册直接违约、整条登录链拿不到 token,这是当时唯一的实测阻塞点;但它是标注了"测试解锁"的权宜值,最终方案(ODID/AAID 或后端放宽)仍未定。

证据(每条带位置):
  1. 修改本体:9b3105a2-85ec-4889-9786-b3c220f06754.jsonl:5199,Edit,new_string 含 `KEY_ANDROID_ID: string = 'android_id'`,时间 2026-07-25T02:59:41.615Z。
  2. 触发指令:同文件:5146,2026-07-25T02:54:51.105Z,`<command-name>/arkts-visual-verify</command-name>` + args「请修复下当前的登录问题,修复完就返回即可」。
  3. 根因判定:同文件:5164,2026-07-25T02:57:23.720Z「F003Repository.ets:385 调 setPrivacyInfo(operators, '', ''),第二个参数 androidId 传空串 → 后端 NOT NULL 列违约 → 游客注册失败」。
  4. 实证依据:agent-abase3-network-f9a03317492be8c4.jsonl:138(2026-07-24T09:46:41.162Z)与 :268,LIVE PROBE body 含 `"androidId":"a1b2c3d4e5f60718"`,HTTP 200、code=0、返回 token。
  5. 原文件写者与口径:agent-abase5-preferences-c92f24144fec6f9d.jsonl:93(2026-07-24T10:38:49.479Z)Write,content 头部「键名值逐字复刻源码,任何情况下都不得改写」,键来源表列 5 个 Kotlin 常量文件;meta.json 显示 agentType=base5-preferences/customAgentType=a2h-migration-worker/model=opus。
  6. 挂起转派链:agent-abase3-network-f9a03317492be8c4.jsonl:264/272 登记 P-BASE3-003「不臆造 UUID 冒充解决……resolve_by=Slice 2 Step 3c」。
  7. 接盘人被明令禁止:agent-aslice2-auth-ac8d92aebe3693fc.jsonl:1(2026-07-24T11:54:37.217Z)任务书硬约束 2「保持挂起、不要臆造取值……但方案需联调确认,你不要擅自定」,且同一段已把 a1b2c3d4e5f60718 的 probe 线索给了它。
  8. 验证与落地:同主会话:5226 编译(hvigorw assembleHap)、:5230「BUILD SUCCESSFUL」、:5231 提交,:5232 返回 commit `c184680`。

无法确认的部分: (1) 题面说改动发生在"修复轮 ff019d8a";实际全目录扫描显示 ff019d8a 及其 146 个子 agent 从未 Write/Edit 过 PreferenceKeys.ets(仅 3 处 tool_result 在 skill 文档里提到该文件名),PreferenceKeys.ets 的唯一两次写入都在 9b3105a2 内 —— 一次是 Base-5 生成,一次是该会话尾部由 `/arkts-visual-verify` 触发的修复段。按时间戳 ff019d8a(07-26)确在 9b3105a2(07-24~25)之后,所以本文按"实际改动者"作答。(2) 改完只做了编译验证,转录里没有改后在设备上真跑通登录、或再打一次 initUser 的实证,是否真解了登录无法确认。(3) 后端是否会因 android_id 与真实 Android 设备号语义不符在生产环境出问题,转录内无信息。

置信: 高 —— 修改点、时间、触发指令、实证依据、原写者与转派链五条均有唯一且互相印证的转录锚点;仅"是否真跑通登录"这一后验环节缺证据。
```