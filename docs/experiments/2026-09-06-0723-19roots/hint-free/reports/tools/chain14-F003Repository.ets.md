```
文件: entry/src/main/ets/repositories/F003Repository.ets  修复方: 主会话(编排/直接写盘)·arkts-visual-verify(__main__:9b3105a2)  修复版本: v11-v12(agent v242/v243)
修复改了什么: 把 collectPrivacyInfo() 里 `setPrivacyInfo(operators, '', '')` 的 androidId 空串换成 `DevicePrefs.getOrCreateAndroidId()`(v11 补 import),并同步新建 `PreferenceKeys.KEY_ANDROID_ID`(v2)与 `DevicePrefs.getOrCreateAndroidId()`(v2,16-hex 生成+持久化);同时把原「按现状传空串、不编造设备标识」的 4 行注释改写为「D-010 测试解锁,最终方案待联调」。
修复的依据: 上游 canonical 登记点自己记的 probe 事实——`network/AppFormInfoManager.ets@v5:151-156`:后端 `USER_INFO.ANDROID_ID` 是 NOT NULL 列,传空串直接 `SQLIntegrityConstraintViolationException` → 游客注册失败 → 拿不到 token → 全部接口不可用;加上主会话 v191 派发词里的活体打靶结论「测试值 androidId="a1b2c3d4e5f60718" 注册成功,后端只要求非空+格式合法」。修复发生在 arkts-visual-verify 阶段的一批「测试解锁」动作中(同段 #1631 commit「解除测试账号被 rele…」)。
被改代码的来源: slice2-auth(agent-aslice2-auth-ac8d92aebe3693fc)在自己 v2 写下 F003Repository@v1(#18457)时写的 5 行(blame@v12 changed);依据是它的派发词硬约束 2「D-010 androidId 是后端阻塞项,Base-3 已留口 P-BASE3-002/003,保持挂起、不要臆造取值……方案需联调确认,你不要擅自定」,以及它 v1 全文读过的 `AppFormInfoManager.ets@v5:156`「本层只保留字段与传参路径,**不臆造 UUID 冒充解决**」。新增的 DevicePrefs 那 23 行是纯新增(sessions:DevicePrefs 链),前一版写者 base5-preferences v8 没写它,因为该键在生成期根本不被允许存在。
生成时为什么没做好: 不是转换错也不是漏读——问题在 spec/策略环节:Base-3 的 D-010 处置策略(P-BASE3-003「传空串挂起、不臆造」)与它自己记录的 probe 事实(空串必然注册失败)自相矛盾,又被主会话 v191 派发词原样固化下发,生成期没有任何一环被授权注入可用值。
是否必要: 必要,空串是实录里 probe 实证会让游客注册整链断死的取值,不改则登录/全部接口在测试环境不可用。
证据(每条带坐标):
  1. diff F003Repository.ets@v12(主会话 v243,#1655):`setPrivacyInfo(operators, '', '')` → `setPrivacyInfo(operators, androidId, '')`;imei 仍空串(注释称 probe 实证后端允许为空)。
  2. blame F003Repository.ets@v12 changed=True:被替换 5 行全部 owner=slice2-auth@文件v1(agent slice2-auth v2,#18457,T+24:06)。
  3. 派发词全文(agent slice2-auth,派发自 主会话·9b3105a2 v191)硬约束 2:D-010「保持挂起、不要臆造取值」「你不要擅自定」,并附打靶线索「后端只要求非空且格式合法」。
  4. AppFormInfoManager.ets@v5:151-156(base3-network 写):NOT NULL / `SQLIntegrityConstraintViolationException` / 拿不到 token / 「不臆造 UUID 冒充解决」;slice2-auth v1 于 #18350(T+23:53)全文读过这一版 —— 它是"读全了仍按令写空串",不是漏读。
  5. 修复同批产物:PreferenceKeys.ets@v2(主会话 v240,#1647)新增 `KEY_ANDROID_ID` 并注明「测试解锁,最终方案待联调」;DevicePrefs.ets@v2(v241,#1649)新增 `getOrCreateAndroidId()`,读时兜底生成 16-hex 并回写;F003Repository.ets@v11(v242,#1653)仅补 import。
  6. 阶段标:v240-v243 均为 arkts-visual-verify(真机验证期),即静态编译/结构审计四道门放行后才暴露的运行期问题。
无法确认的部分: 触发这次修复的直接信号无法确认——#1631(T+37:53)到 #1632(T+38:53)有约 1 小时无任何动作,账本里既无收件记录也无真机报错/probe 动作;修复后是否再做过活体打靶复验也无记录(v12 之后只有 v244 的读取)。另外 F003Repository 有一处 v8「实录外修改」与 v44 的脚本黑盒调用(#18598),未展开核对,不涉及被修的这 6 行。
置信: 高,改了什么/谁写的/凭什么写与凭什么改四条都落在 diff、blame、派发词全文与 canonical 文件同版原文上;仅"触发信号"一环缺证据。
```