```
文件: entry/src/main/ets/preferences/PreferenceKeys.ets  修复方: 主会话(编排/直接写盘)·arkts-visual-verify(__main__:9b3105a2, 其 v240)  修复版本: v2(T+38:56, #1647)
修复改了什么: 纯新增 9 行——常量 `KEY_ANDROID_ID='android_id'` 及其注释；同一批还写了 DevicePrefs.ets@v2(新增 getOrCreateAndroidId()，util.generateRandomUUID 取 16 位小写 hex、读时兜底回写)与 F003Repository.ets@v11/v12(import DevicePrefs，把 androidId 注入 setPrivacyInfo)。
修复的依据: D-010(spec/decision-ledger.md@v2:23，C17：「androidId 后端 NOT NULL，鸿蒙无等价 API——阻塞，方案待定」，状态 pending-approval)+ 代码注释自称的「Base-3 活体打靶实证后端只校验非空+格式合法(16-hex)」；自我定性为「测试解锁」，最终方案待联调。
被改代码的来源: 纯新增(sessions 行级归属「纯新增 9 行」)。前一版 PreferenceKeys.ets@v1 由 base5-preferences v1 写(T+22:35)——android_id 在安卓源码里不是 MMKV 键(出自 Settings.Secure.ANDROID_ID)，而它的派发词(主会话 v182)把输入限定为 feature-base.md §5 + Android MMKV 键定义 + Base-1/Base-4 产出，硬约束是「键名与源码逐字相同」「D0 照搬不修」，故不该也没有这个键。真正的槽位归 Base-3：主会话 v177 派发词明令 D-010「照常留字段与传参路径…**不要臆造一个 UUID 就当解决了**」，base3-network 遵办并登记占位 P-BASE3-003。
生成时为什么没做好: 卡在决策环而非转换环——D-010 全程停在 pending-approval「阻塞、方案待定」，执行期按占位规则合法放行(传空串)，且 Base-5 的派发词没把 decision-ledger/D-010 列为输入、Base-5 也从未读过它，于是偏好层连 android_id 的槽位都不存在。
是否必要: 必要(临时性)。后端列 NOT NULL 而原实现传空串，游客注册链在测试环境不通；但它正是 Base-3 派发词禁止的「臆造 UUID」，修复方自己标注为测试解锁、终态待定，故必要而非终局。
证据(每条带坐标):
  1. PreferenceKeys.ets@v2 diff(主会话 v240，#1647)：+9 行 KEY_ANDROID_ID，注释直书「D-010…Base-3 活体打靶实证后端只校验非空+格式合法…⚠测试解锁」。
  2. sessions(file=PreferenceKeys.ets)：生成方 base5-preferences(T+22:35 v1)、修复方 __main__:9b3105a2(T+38:56 v2)，行级归属「纯新增 9 行」。
  3. spec/decision-ledger.md@v2 第 23 行：D-010 · C17 · 「androidId 后端 NOT NULL，鸿蒙无等价 API——阻塞，方案待定」，status=pending-approval(与 D-011/D-012 并列，全表其余皆 approved)。
  4. base3-network(agent-abase3-…be8c4) 派发词(主会话 v177)「后端阻塞项」段：D-010 只留字段与传参路径、标 //FWD-REF、「不要臆造一个 UUID 就当解决了——那会让问题在联调时才暴露」；其收尾输出第 3 点复述「androidId(D-010) 与 channel(D-011) 按要求只留字段与传参路径，未臆造取值」。
  5. F003Repository.ets@v12 diff 的删除行(即生成期原状)：「androidId 的取值方案是 D-010 后端阻塞项，唯一 canonical 登记点在 network/AppFormInfoManager.ets 的 P-BASE3-003…本方法按现状传空串…不在此处编造设备标识」。
  6. base5-preferences 派发词(主会话 v182)「输入来源」只列 feature-base.md §5 / Android MMKV 源码 / Base-1 / Base-4，无 decision-ledger；其 v1 读取集(#2913–#3046)确无 spec/decision-ledger.md，且该文件 @v2 的 17 个下游读者名单里也没有 base5-preferences。
  7. DevicePrefs.ets@v2 diff + F003Repository.ets@v11/@v12 diff：三处同一分钟(T+38:56–38:57)成组落地，是同一次修复的完整闭环。
无法确认的部分: ① 触发这次修改的具体运行时失败(真机截图/后端报错/联调日志)在账本里找不到对应动作——主会话 v240 窗口(#1629–#1645)只读了 F013Service/F003Repository/AppFormInfo/DevicePrefs 与 PreferenceKeys@v1 自身，没有任何 probe 或失败日志的读；② 「Base-3 活体打靶实证后端只校验非空+格式合法(16-hex 即可)」这条依据无法核实——base3-network 收尾只记了 POST /user/initUser 活体打靶 HTTP 200 / 内层 status=0 / 返回 32 位 token，没有记录针对 androidId 取值的对照实验；③ decision-ledger.md@v2 是「实录外修改」(T+13:42)，D-010 是否在 v1(主会话 v62, T+4:55)就已写入，未核。
置信: 中高——修复内容、D-010 依据、Base-5/Base-3 的授权边界与占位链路都有直接坐标且互相印证；扣分只在触发事件与「后端只校验格式」这条事实依据无实录支撑。
```