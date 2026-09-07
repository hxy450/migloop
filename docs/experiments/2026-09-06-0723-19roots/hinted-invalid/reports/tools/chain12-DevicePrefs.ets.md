```
文件: entry/src/main/ets/preferences/DevicePrefs.ets  修复方: 主会话(编排/直接写盘) · arkts-visual-verify(__main__:9b3105a2)  修复版本: v2
修复改了什么: 纯新增 23 行 static getOrCreateAndroidId()——读 KEY_ANDROID_ID，空白则用 util.generateRandomUUID 去连字符取前 16 位生成 16-hex 并回写，复刻同文件 getOrCreateMarkId 的读时兜底；配套 PreferenceKeys.ets@v2 新增 KEY_ANDROID_ID='android_id'，F003Repository.ets@v11/v12 把 setPrivacyInfo(operators,'','') 改成注入该值。
修复的依据: 自述依据写在 PreferenceKeys.ets@v2 与 F003Repository.ets@v12 注释里——后端 USER_INFO.ANDROID_ID 是 NOT NULL 列、HarmonyOS 无 Settings.Secure.ANDROID_ID 等价 API，而「Base-3 活体打靶实证后端只校验非空+格式合法」，故按 D-010「测试解锁」先注入稳定值让游客注册链在测试环境可通；同段前一步(v239 · commit #1631)刚接线 debug 开关「解除测试账号被 release 拦截」，是同一测试解锁动作。
被改代码的来源: DevicePrefs 本身是纯新增——v1 写者 base5-preferences v8(#3063) 的派发词把输入限定为 feature-base §5 + MMKV 读写点，收尾 keys_count=36 全是 MMKV 键，androidId 在 Android 侧取自 Settings.Secure 而非 MMKV，不写它是范围内的正确取舍。真正被这次改掉的等价决策在 F003Repository：blame@v12 显示被替换 5 行 owner=slice2-auth@v1，它写「传空串、不在此处编造设备标识、唯一 canonical 登记点 P-BASE3-003」，依据是主会话 @v191 给它的派发词硬约束「D-010…保持挂起、不要臆造取值…你不要擅自定」。
生成时为什么没做好: 不是转换错也不是漏读，而是断在编排层的决策回写这一环——主会话派发时已握有「活体打靶 androidId="a1b2c3d4e5f60718" 注册成功，后端只要求非空+格式合法」这条实证，却仍把 D-010 挂起且没回写 decision-ledger / 解掉 P-BASE3-003，16 小时后才由它自己在返修期解锁。
是否必要: 必要，后端 NOT NULL 列 + 打靶已证格式即可通过，不注入该字段恒为空串；但它绕过了自己定的「联调敲定前挂起」纪律，且属带债解锁。
证据(每条带坐标):
  1. diff DevicePrefs.ets@v2(主会话 v241 · #1649 · T+38:57)：+23 行 getOrCreateAndroidId，注释自标「D-010 测试解锁 / 最终取值方案待联调与后端敲定」。
  2. diff PreferenceKeys.ets@v2(主会话 v240 · #1647)：新增 KEY_ANDROID_ID，注释「Base-3 活体打靶实证后端只校验非空+格式合法（16 位十六进制即可）」。
  3. diff F003Repository.ets@v11/@v12(主会话 v242/v243)：加 import DevicePrefs，并把 setPrivacyInfo(operators,'','') 换成注入 getOrCreateAndroidId()——修复在本文件之外完成接线。
  4. blame F003Repository.ets@v12 changed=True：被替换 5 行全部 slice2-auth@v1；原文见 action(__main__:9b3105a2, #1636) —— 「D-010 后端阻塞项…唯一 canonical 登记点 P-BASE3-003…不在此处编造设备标识」。
  5. agent slice2-auth v1 派发词(派发自主会话 @v191)硬约束 2：「保持挂起、不要臆造取值；参考线索：Base-3 活体打靶用测试值 androidId="a1b2c3d4e5f60718" 注册成功…但方案需联调确认，你不要擅自定」——修复方用的正是这条它当初禁用的线索，16-hex 同形。
  6. agent base5-preferences v8 派发词与收尾(#3063)：输入=feature-base §5 + MMKV 读写点，36 键全为 MMKV 键，androidId 不在其中——DevicePrefs@v1 不含它属范围判断而非遗漏。
  7. 登记点未同步：network/AppFormInfoManager.ets 末版 v9 停在 T+28:33(group2-closer)、spec/decision-ledger.md 末次变更 T+13:42(实录外修改)，而主会话 v240–v243 只写了 PreferenceKeys / DevicePrefs / F003Repository，P-BASE3-003 与 D-010 均未更新。
无法确认的部分: ①「空 androidId 会被后端拒」没有实录证据——打靶用的是测试值，只有 imei 有「probe 实证允许为空」；②主会话 v239–v243 窗口内无可见收件/用户指令，触发这次改动的直接指令无法确认;③P-BASE3-003 是否在 placeholder-registry 中被标记解除，修复期无写记录，无法确认。
置信: 高——修复 diff、配套接线 diff、被改行 blame 与原写者派发词原文均有坐标可核；仅触发指令与空值实际后果两点缺证。
```