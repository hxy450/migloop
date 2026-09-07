```
文件: entry/src/main/ets/preferences/DevicePrefs.ets  修复方: 主会话(编排/直接写盘)·arkts-visual-verify(__main__:9b3105a2)  修复版本: v2(agent v241, #1649, T+38:57)
修复改了什么: 纯新增 23 行 `getOrCreateAndroidId()` —— 复刻 `getOrCreateMarkId` 的读时兜底,生成并回写一个稳定的 16 位小写十六进制值;同一批还加了 `PreferenceKeys.ets@v2` 的 `KEY_ANDROID_ID`(v240)、并在 `F003Repository.ets@v12`(v243)把 `setPrivacyInfo(operators, '', '')` 的空串换成该值。
修复的依据: Base-3 的活体打靶原始 stdout(base3-network #2580):真发 `POST /user/initUser`,body 里 `androidId="a1b2c3d4e5f60718"` → HTTP 200、内层 `status=0`、返回 32 位 token,证明后端只校验非空+格式合法;配合 D-010「后端 `USER_INFO.ANDROID_ID` 是 NOT NULL 列、HarmonyOS 无 `Settings.Secure.ANDROID_ID` 等价 API」。触发是主会话自查 #1632(T+38:53)grep「androidId 当前注入值」,看见 F003Repository:385 仍是空串。
被改代码的来源: DevicePrefs 这一侧是纯新增;前一版写者 base5-preferences v8(#3063)没写,是因为它的派发词(主会话@v182)把输入限定为 `feature-base.md §5` + MMKV 读写点、硬约束「键名与源码逐字相同」,而 `android_id` 在安卓侧根本不是 MMKV 键(来自 `Settings.Secure`),不在其任务面内。同一修复在 F003Repository@v12 替换掉的 5 行,blame 全部归 slice2-auth@v1 —— 它是按派发词(主会话@v191 硬约束 #2)「保持挂起、不要臆造取值…你不要擅自定」写的空串。
生成时为什么没做好: 卡在编排环的阻塞项决策,不在转换/读取环 —— 主会话在 @v177、@v191 两份派发词里把 D-010 定为「留口不解、不要臆造」,而解阻所需的活体打靶证据 Base-3 早在 #2580(T+21:43)就拿到了,证据一直在手却没回流去改这条约束;base3-network 与 slice2-auth 都是严格执行,两者都没错。
是否必要: 必要 —— 后端该列 NOT NULL 而生成态一直注入空串,#2580 已实证 16-hex 可通,不补则游客注册链在测试环境走不通。
证据(每条带坐标):
  1. DevicePrefs.ets@v2 diff(主会话 v241,#1649):新增 `getOrCreateAndroidId()`,注释自述「Base-3 活体打靶验证过后端接受的格式」「测试解锁(D-010)」。
  2. PreferenceKeys.ets@v2 diff(主会话 v240,#1647)新增 `KEY_ANDROID_ID`;F003Repository.ets@v12 diff(v243)把 `setPrivacyInfo(operators, '', '')` 改为注入 `DevicePrefs.getOrCreateAndroidId()`。
  3. action(base3-network, #2580):LIVE PROBE body `"androidId":"a1b2c3d4e5f60718"` → HTTP 200 / 内层 `status=0` / token 长度 32。
  4. blame F003Repository.ets@v12 changed=True:被替换的 5 行(v11 的 369-372、385)全部 owner=slice2-auth@v1。
  5. slice2-auth 派发词(派发自主会话@v191)硬约束 #2:「保持挂起、不要臆造取值……参考线索:Base-3 活体打靶用测试值 `androidId="a1b2c3d4e5f60718"` 注册成功,说明后端只要求非空且格式合法。但方案需联调确认,你不要擅自定。」
  6. base3-network 派发词(主会话@v177)后端阻塞项 D-010:「照常留字段与传参路径……不要臆造一个 UUID 就当解决了」;其收尾输出:「`androidId`(D-010) 与 `channel`(D-011) 按要求只留字段与传参路径,未臆造取值」。
  7. base5-preferences 派发词(主会话@v182)输入源=`feature-base.md §5`+MMKV 读写点、硬约束 1「键名与源码逐字相同」;其收尾 notes 只补了 `oaid`/`sensitive_city`/`screen_touch_count`/`strategy_type_<N>` 这些源码实有的键。
无法确认的部分: 账本里没有「androidId 传空串导致 initUser 失败」的实测 —— #2580 只打过非空 16-hex(打过空值的是 `imei`),必要性靠 NOT NULL 约束+该 probe 推得,非直接反证;T+37:53→T+38:53 这一小时里主会话收到什么(是否有真机复现/用户指令)账本无收件记录,只看得到 #1632 的自查 grep;修复未同步动 `network/AppFormInfoManager.ets`(末版 v9 @T+28:33)里的 `P-BASE3-003` 登记,placeholder-registry 是否同步无法确认。
置信: 高 —— 修复版 diff、被替换行 blame、两份派发词原文与活体打靶原始 stdout 四路互证,唯一未闭合的是空值失败的直接实测。
```