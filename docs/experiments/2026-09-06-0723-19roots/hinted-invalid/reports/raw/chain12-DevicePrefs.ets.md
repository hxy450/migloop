```
文件: entry/src/main/ets/preferences/DevicePrefs.ets  修复方: 主会话(编排/直接写盘) · arkts-visual-verify(9b3105a2-85ec-4889-9786-b3c220f06754)  修改时间: 2026-07-25T02:59:57.729Z
修复改了什么: 在 DevicePrefs 里**新增** `getOrCreateAndroidId()`——复刻 `getOrCreateMarkId()` 的「读时兜底+立即回写」模式,用 `util.generateRandomUUID(true)` 去连字符取前 16 位产一个稳定持久的 16-hex 设备标识;配套新增 `PreferenceKeys.KEY_ANDROID_ID`,并把 `F003Repository.collectPrivacyInfo` 的 `setPrivacyInfo(operators, '', '')` 改成传该实值。
修复的依据: 用户 `/arkts-visual-verify 请修复下当前的登录问题`(主:5146,02:54:51.105Z);排查后判定 D-010 是登录阻塞根因——「androidId 传空串 → 后端 NOT NULL 列违约 → 游客注册失败 → 拿不到 token」,并援引 Base-3 活体打靶「后端只校验非空+格式合法,16-hex 可注册成功」作为可注入任意合法值的实证(主:5164,02:57:23.720Z)。
被改代码的来源: DevicePrefs.ets 由子 agent **base5-preferences** 于 2026-07-24T10:42:33.170Z 一次性 Write(base5:110),自述「源:`MMKVUtil.kt`(markId / oaid / sensitiveCity / huoshanAppId / installSource)」——Android 的 androidId 来自 `Settings.Secure.ANDROID_ID` 而非 MMKV,base5 按源码对位没有可写的键,故本次是**纯新增**、未覆盖任何旧代码。真正被改掉的是同批 F003Repository 里 slice2-auth 写的空串传参及其「不在此处编造设备标识」注释(slice2:194/351)。
生成时为什么没做好: 卡在「谁来落 D-010 取值」这一环——Base-3 把 androidId 登记为后端阻塞占位 P-BASE3-003、明写「**不臆造 UUID 冒充解决**」且指派 resolve_by=Slice 2 Step 3c(base3:169/272),而编排方给 slice2-auth 的任务约束又原话要求「保持挂起、不要臆造取值……你不要擅自定」(slice2:1),指定的落地点被合同性地禁止落地,于是空串一路留到运行期。
是否必要: 必要——空 androidId 使 `initUser` 100% 失败是 2026-07-23 活体 probe 实证(非静态推断,base3:13/23/45 引 chain-auth §7),不注入值登录链根本走不通;但它是「测试解锁」,最终方案(系统 ODID/AAID 或后端放开约束)仍待联调,agent 自己在注释和 commit 里都标了这点。
证据(每条带位置):
  1. 修复本体:主会话 9b3105a2-*.jsonl:5203 Edit(02:59:57.729Z)新增 `getOrCreateAndroidId()`;file-history-delta 在 :5202(backupTime 02:59:58.667Z)。
  2. 触发:主 :5146(02:54:51.105Z)`/arkts-visual-verify` + 「请修复下当前的登录问题,修复完就返回即可」。
  3. 定位与判据:主 :5156/:5157 grep 出 `F003Repository.ets:385 setPrivacyInfo(operators, '', '')`;主 :5164 给出 D-010 阻塞结论 + 引 Base-3 打靶。
  4. 打靶实证:base3-network:135/138(09:46:25/09:46:41)离线对账 + `POST http://dev-api.whiap.cn/user/initUser` 用 `androidId="a1b2c3d4e5f60718"` 得 HTTP 200、code 0、返回 token/userId。
  5. 空串必失败的原始证据:base3-network:13/23/45(09:39–09:40)读 chain-auth.md §7——「`USER_INFO.ANDROID_ID` 是 NOT NULL 列,传空直接 `SQLIntegrityConstraintViolationException`,initUser 100% 失败」,来自 2026-07-23 活体探针。
  6. 「不许臆造」的上游规矩:base3-network:169(09:53:45.300Z)写 `AppFormInfoManager.setPrivacyInfo` 注释「**不臆造 UUID 冒充解决**」,:272 registry 条目 P-BASE3-003 resolve_by=Slice 2 Step 3c;slice2-auth:1(11:54:37.217Z)任务硬约束第 2 条「保持挂起、不要臆造取值……你不要擅自定」。
  7. 前一版写法:slice2-auth:194(12:09:13.814Z)Write F003Repository、:351 可见 `setPrivacyInfo(operators, '', '')`;DevicePrefs 原文见 base5-preferences:110(10:42:33.170Z)。
  8. 修复后校验:主 :5227(03:02:14Z)`hvigorw assembleHap` BUILD SUCCESSFUL;:5231 提交 c184680「fix(D-010)…(测试解锁,待后端敲定最终方案)」。
无法确认的部分: 修复只做了**编译**验证,转录里没有改后重跑 initUser/登录的活体证据(用户要求「修复完就返回」,主:5238 只说编译 PASS 并让用户重装后自测),故「登录确已打通」无法确认;16-hex 的「稳定至重装/清数据」语义也未经实测(HarmonyOS Preferences 随应用卸载清除,注释里这句偏乐观,无转录证据);另外无法确认此前是否有人在鸿蒙侧真跑过空 androidId 的失败复现(证据均指向 2026-07-23 的 Android/脚本侧 probe)。
置信: 高——修改点、触发提示、上游占位登记与「禁止臆造」的指令链、原始 probe 证据都能在转录里逐条定位到行号与时间戳;唯一降档因素是修复效果未经运行时验证,已单列。
```