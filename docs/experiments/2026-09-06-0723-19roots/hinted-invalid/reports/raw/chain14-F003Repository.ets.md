```
文件: entry/src/main/ets/repositories/F003Repository.ets  修复方: 主会话(编排/直接写盘) · arkts-visual-verify(session 9b3105a2-85ec-4889-9786-b3c220f06754)  修改时间: 2026-07-25T03:00:19.095Z(+03:00:41.345Z 第二处)
修复改了什么: 两处编辑——补 `import { DevicePrefs }`(5214),并把 `collectPrivacyInfo()` 里 `AppFormInfoManager.setPrivacyInfo(operators, '', '')` 的第 2 参从空串改成 `DevicePrefs.getOrCreateAndroidId()`(5221),同轮还在 DevicePrefs/PreferenceKeys 新增了该生成器与 `KEY_ANDROID_ID`,注释重写为「测试解锁,最终方案待联调」。
修复的依据: 用户 `/arkts-visual-verify 请修复下当前的登录问题`(:5146);主会话 grep 出 `F003Repository.ets:385` 传空串后判定(:5164):后端 `USER_INFO.ANDROID_ID` 是 NOT NULL 列 → 游客注册失败 → 拿不到 token → 登录全链阻塞,而 Base-3 活体打靶已实证「非空 + 16-hex 即被接受」;实现照抄已有的 `DevicePrefs.getOrCreateMarkId()` 读时兜底模式(:5180-5181)。
被改代码的来源: 生成轮子 agent `slice2-auth`(a2h-migration-worker,opus)一次性 Write 出整个 F003Repository.ets(subagents/agent-aslice2-auth:193,2026-07-24T12:09:13.743Z),空串与那段「不在此处编造设备标识」的注释是它写的。它这么写不是疏忽:其任务提示词(同文件:1)明令「D-010/D-011 保持挂起、不要臆造取值……你不要擅自定」,并在同一段里就告诉了它 Base-3 打靶用 `a1b2c3d4e5f60718` 注册成功。上游是 Base-3 登记的 `P-BASE3-003`(agent-abase3-network:264):同一条记录里既写明「空串直接 SQLIntegrityConstraintViolationException」,又立下「不臆造 UUID 冒充解决」的口径,并把它派成 forward-ref、resolve_by=Slice 2 Step 3c。
生成时为什么没做好: 卡在 Base-3 的占位登记 → slice2-auth 任务提示词这一环:同一条 P-BASE3-003 里「空串必失败」和「不许自己取值」并存,resolve_by 又指回被明令禁止解决的 Slice 2,于是这个占位在整条生成链里无人可解,最终落盘的是打靶已证必失败的值。
是否必要: 必要——探针实证空串会让游客注册直接违约、token 拿不到,登录链一定不通,不改则整个 app 无法联调。
证据(每条带位置):
  1. 修复的两处编辑:9b3105a2-*.jsonl:5214(uuid 153d90cc,2026-07-25T03:00:19.095Z,加 DevicePrefs import)、:5221(03:00:41.345Z,`setPrivacyInfo(operators, androidId, '')`)。
  2. 触发与判定:9b3105a2-*.jsonl:5146(02:54:51.105Z 用户「请修复下当前的登录问题」)、:5157(grep 出 `385: setPrivacyInfo(operators, '', '')`)、:5164(02:57:23.720Z「D-011 通、D-010 空串 → 登录全链阻塞」)。
  3. 原始写者:subagents/agent-aslice2-auth-ac8d92aebe3693fc.jsonl:193(2026-07-24T12:09:13.743Z 单次 Write,含空串调用与「不在此处编造设备标识」注释)。
  4. 禁止其解决的指令:同文件:1(11:54:37.217Z)「Base-3 已留口 P-BASE3-002/003,保持挂起、不要臆造取值……但方案需联调确认,你不要擅自定」。
  5. 上游口径与矛盾:subagents/agent-abase3-network-f9a03317492be8c4.jsonl:264(10:05:09.293Z placeholder-registry「空串直接 SQLIntegrityConstraintViolationException…不臆造 UUID 冒充解决,resolve_by=Slice 2 Step 3c」)。
  6. 「16-hex 可用」的实证:同文件:277(10:09:33.960Z 活体打靶 `androidId:"a1b2c3d4e5f60718"` → 内层 status=0、拿到 token、userId=28309661)。
  7. 修复后的验证只到编译:9b3105a2-*.jsonl:5227(03:02:14.386Z BUILD SUCCESSFUL)、:5232(提交 c184680),未再跑活体打靶或真机登录。
无法确认的部分: 修复后是否真的打通了登录——转录里只有编译通过和提交,没有任何 post-fix 的活体请求或用户回执;主会话是从上一轮「手机号校验」修好后推断下一层阻塞,并未观察到 androidId 导致的实际报错报文。另外 16-hex 值在真机 Preferences 上「稳定至重装/清数据」这一说法(注释所称语义等价 ANDROID_ID)无转录证据支持,鸿蒙 Preferences 随应用卸载清除,该注释很可能偏乐观。
置信: 高——改动内容、依据链、原始写者与那条自相矛盾的占位口径都能逐条落到具体行号与时间戳;仅「改完是否真跑通」一项无证据,已单列。
```