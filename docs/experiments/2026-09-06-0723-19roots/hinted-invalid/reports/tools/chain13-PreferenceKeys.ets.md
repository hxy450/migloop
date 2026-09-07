```
文件: entry/src/main/ets/preferences/PreferenceKeys.ets  修复方: 主会话(编排/直接写盘) · arkts-visual-verify(__main__:9b3105a2)  修复版本: v2
修复改了什么: 在 KEY_MARK_ID 之后纯新增 9 行——新键 `KEY_ANDROID_ID = 'android_id'` 及其注释;同一分钟内联动写了 DevicePrefs@v2(新增 `getOrCreateAndroidId()`,16-hex 读时兜底回写)与 F003Repository@v11/v12(把 `setPrivacyInfo(operators, '', '')` 改成注入该值)。
修复的依据: 写前读 F003Repository@v10[358-389](#1636)看到 androidId 当前传空串、标为 D-010 后端阻塞项(`USER_INFO.ANDROID_ID` NOT NULL);援引 Base-3 活体打靶结论"后端只校验非空 + 格式合法(16 位十六进制)",并自我限定为「测试解锁,最终方案待联调敲定」(PreferenceKeys@v2 第 127-132 行 / action #1647 的 new_string)。
被改代码的来源: PreferenceKeys 这 9 行是纯新增;v1 写者 base5-preferences v1(#3049)的派发词(主会话@v182)把权威输入定为 `feature-base.md §5` + Android MMKV 键定义、验收为"覆盖 §5 全部键、键名与源码逐字相同",而 android_id 在 Android 侧根本不是 MMKV 键(出自 `Settings.Secure`),故不在其范围(收尾:34 静态 + 2 动态键)。真正被推翻的是同批 F003Repository 里 slice2-auth@v1 写的 5 行"不在此处编造设备标识、按现状传空串",而那 5 行是照主会话@v191 派发词硬约束 2「D-010 保持挂起、不要臆造取值」写的。
生成时为什么没做好: 不是 spec 错/漏读/转换错,而是编排环的决策——主会话在 @v191 派发时已握有 Base-3 打靶证据仍把 D-010 定为"挂起",生成期因此留下空 androidId,16 小时后同一主会话在真机验证阶段自行反转。
是否必要: 存疑,方向有据(NOT NULL 列 + 打靶实证,且由原决策方自己解禁)但实录里没有"空串确实导致注册失败"的活体记录,且是临时解锁而非终态方案。
证据(每条带坐标):
  1. PreferenceKeys.ets@v2 diff / action(__main__:9b3105a2, #1647):Edit 原文只在 KEY_MARK_ID 后插入 KEY_ANDROID_ID 及注释,9 行纯新增。
  2. blame F003Repository.ets@v12(changed):被替换的 5 行全部 owner=slice2-auth@v1,含"不在此处编造设备标识"与 `setPrivacyInfo(operators, '', '')`;diff@v12 改为注入 `DevicePrefs.getOrCreateAndroidId()`。
  3. slice2-auth 派发词(派发自主会话@v191)硬约束 2:"D-010 … Base-3 已留口 P-BASE3-003,保持挂起、不要臆造取值 … 打靶用测试值 androidId=\"a1b2c3d4e5f60718\" 注册成功,说明后端只要求非空且格式合法,但方案需联调确认,你不要擅自定"。
  4. base5-preferences 派发词(派发自主会话@v182)+ 收尾:输入=feature-base §5,验收"覆盖 §5 全部键 / 键名逐字相同",keys_count=34 静态 + 2 动态,无任何设备标识生成职责。
  5. 主会话 v240 的写前读集(#1636 F003Repository@v10、#1638/#1641 DevicePrefs@v1、#1643/#1645 PreferenceKeys@v1[▲旧版 v1/2]):依据全部来自工程内既有注释,未读 canonical 登记点 network/AppFormInfoManager.ets。
  6. 联动版本:DevicePrefs@v2(#1649 T+38:57)16-hex 生成+回写、F003Repository@v11(#1653)加 import、@v12(#1655)注入——三处同批完成。
  7. 残留:PreferenceKeys@v2 的 `ALL_STATIC_KEYS`(259-308 行)仍是 34 键、注释仍写"34 个静态键的全集",新键未入列;network/AppFormInfoManager.ets 仍停在 v9(group2-closer, T+28:33),canonical P-BASE3-003 未同步更新。
无法确认的部分: 触发这次修改的直接输入(真机/联调失败日志或用户指令)不在 v238–v240 的动作记录里,因此无法确认空 androidId 是否真的让注册链失败;P-BASE3-003 的登记原文未展开,打靶结论只见于派发词与 F003Repository@v10 的转述。
置信: 中,写者、依据与被推翻的原决策都有明确坐标,但缺触发证据与 P-BASE3-003 原文,故"是否必要"只能停在存疑。
```