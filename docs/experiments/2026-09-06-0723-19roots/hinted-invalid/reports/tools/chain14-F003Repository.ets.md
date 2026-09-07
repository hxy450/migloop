```
文件: entry/src/main/ets/repositories/F003Repository.ets  修复方: 主会话(编排/直接写盘) · arkts-visual-verify(__main__:9b3105a2)  修复版本: v11-12
修复改了什么: v11 补 `import { DevicePrefs }`;v12 把 `collectPrivacyInfo()` 里的 `setPrivacyInfo(operators, '', '')` 改成注入 `DevicePrefs.getOrCreateAndroidId()`(新生成的稳定 16-hex 值),并把原来「D-010 阻塞、按现状传空串」的注释块改写为「测试解锁 + 最终方案待联调」。
修复的依据: base3-network 在 canonical 登记点 `network/AppFormInfoManager.ets@v9:153-158`(P-BASE3-003)已实证:后端 `USER_INFO.ANDROID_ID` 是 NOT NULL 列,probe 传空串直接 `SQLIntegrityConstraintViolationException` → 游客注册失败 → 拿不到 token → 全部接口不可用;同处记录 Base-3 活体打靶显示后端只校验非空 + 格式合法。修复方据此在 v240/v241 先建 `PreferenceKeys.ets@v2` 的 `KEY_ANDROID_ID`、`DevicePrefs.ets@v2` 的 `getOrCreateAndroidId()`(16-hex,读时兜底回写),再回填本文件。
被改代码的来源: 被替换的 5 行全部是 slice2-auth 在文件 v1(agent v2,T+24:06)写的。它是照派发词执行:主会话 @v191 给 slice2-auth 的硬约束 #2 明写「D-010 androidId 是后端阻塞项,Base-3 已留口 P-BASE3-003,**保持挂起、不要臆造取值**……方案需联调确认,你不要擅自定」;canonical 点自身也写着「**不臆造 UUID 冒充解决**」。即传空串是被显式命令的,不是疏漏。
生成时为什么没做好: 卡在编排环——主会话 v191 的阻塞项处置策略把 D-010 定为「须与后端敲定、禁止臆造」并推给 F003 联调,尽管 Base-3 的 probe 早已实证空串必然导致注册失败,生成期没有任何一方被授权闭合它。
是否必要: 必要,空串会让游客注册链在真机上直接失败(probe 实证),不改则登录测试无法进行;但它是修复方自标的临时「测试解锁」,并推翻了 P-BASE3-003「不臆造」的既定裁决。
证据(每条带坐标):
  1. diff F003Repository.ets@v11 / @v12:v11 加 DevicePrefs import;v12 用 `const androidId = DevicePrefs.getOrCreateAndroidId()` 替掉第二个空串实参。
  2. blame F003Repository.ets@v12 changed=True:被替换 5 行(v11 的 369-372、386)全部 owner = slice2-auth@文件v1。
  3. agent __main__:9b3105a2 v240→v243:同一分钟内依次写 PreferenceKeys.ets@v2(KEY_ANDROID_ID)、DevicePrefs.ets@v2(getOrCreateAndroidId)、F003Repository.ets@v11/v12;DevicePrefs@v2 注释自称「⚠ 测试解锁(D-010),最终取值方案待联调与后端敲定」。
  4. AppFormInfoManager.ets@v9:153-158 + :166(base3-network 建的 P-BASE3-003):NOT NULL 列 / 空串 SQLIntegrityConstraintViolationException / 「不臆造 UUID 冒充解决」/ resolve_by=backend-androidid-decision。
  5. agent agent-aslice2-auth-…@v2 的派发指令全文(派发自 __main__:9b3105a2@v191)硬约束 #2:D-010 保持挂起、参考线索是打靶测试值 `a1b2c3d4e5f60718` 注册成功、「你不要擅自定」。
  6. 喂 v240–v243 的读取集(agent __main__:9b3105a2 窗口 v237–v243)只含 F003Repository@v10、AppFormInfo.ets@v3、DevicePrefs@v1、PreferenceKeys@v1,不含 AppFormInfoManager.ets;该文件仍停在 v9(07-24T16:36),P-BASE3-003 的 FWD-REF 与「不臆造」注释未随修复同步。
无法确认的部分: 触发这次修复的直接现场信号(真机注册/登录失败的实际报文)不在因果窗口的读取记录里,修复方对「NOT NULL」的引用无法确认是当场重读 P-BASE3-003 还是沿用会话内已有上下文;另外账本无后续版本,无法确认这个临时值是否在联调后被替换。
置信: 高,修复内容、修复依据、被改行原作者与其禁令来源都各有明确坐标且互相印证,只有触发时刻的现场信号缺一环。
```