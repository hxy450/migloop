| 根 | 组 | 费用 $ | 轮 | 调用 | 返回字 | 时长 s | 错误 |
|---|---|---|---|---|---|---|---|
| EntryAbility.ets | tools | 1.71 | 27 | 26 | 73362 | 392 |  |
| EntryAbility.ets | raw | 2.25 | 24 | 23 | 139264 | 417 |  |
| GuidePage.ets | tools | 2.10 | 35 | 34 | 74159 | 398 |  |
| GuidePage.ets | raw | 2.22 | 30 | 29 | 117015 | 400 |  |
| HomeTabComponent.ets | tools | 1.44 | 30 | 29 | 63096 | 275 |  |
| HomeTabComponent.ets | raw | 2.09 | 32 | 31 | 90482 | 408 |  |
| MemberCenterPage.ets | tools | 1.25 | 30 | 29 | 43826 | 262 |  |
| MemberCenterPage.ets | raw | 2.16 | 25 | 24 | 114977 | 367 |  |
| SplashPage.ets | tools | 1.41 | 31 | 30 | 52663 | 288 |  |
| SplashPage.ets | raw | 2.91 | 36 | 35 | 117182 | 536 |  |
| EntryAbility.ets | tools | 1.32 | 25 | 24 | 57604 | 250 |  |
| EntryAbility.ets | raw | 1.67 | 26 | 25 | 84147 | 343 |  |
| 合计 | tools | 9.23 | 178 | 172 | | 1865 | |
| 合计 | raw | 13.30 | 173 | 167 | | 2470 | |

| 根 | 环数 工具/原始 | 共同环 / 判定一致 | 进入点同环 | 可核 工具/原始 | 一致性 工具/原始 | 更可信 | 更可行动 | 冲突 |
|---|---|---|---|---|---|---|---|---|
| EntryAbility.ets | 13/10 | 9 / 6 | False | 4/5 | 3/4 | control | treat | 8 |
|   | 进入点: A 的进入点是环3(主会话 v175 派发词只给『可临时 barrel 自验、收尾必须移除』、缺 ArkTS elide 未使用 import 这一条),B 的进入点是环1(skill 未规定共享 WindowModel 的归属与建立时机,导致 7 个 converter + entry-setup 各造一份、共 8  | | | | | | | |
| HomeTabComponent.ets | 8/10 | 7 / 6 | True | 4/5 | 4/5 | control | control | 4 |
|   | 进入点: 主链进入点同为生成轮 conv-hometab(agent-aconv-hometab-afeccbf00da93597)首写 Image().width('100%').objectFit(ImageFit.Contain)，且两份给的理由同构：adjustViewBounds="true" 已读进上下文并被抄进注释 | | | | | | | |
| GuidePage.ets | 8/9 | 7 / 6 | False | 5/4 | 4/4 | control | control | 4 |
|   | 进入点: 进度条那股完全同环同判：都锁定 stage0-resources 已 cat 到三层 <size android:height="4dp"/>（A 环8 :154-155 / B 环4 #23081@L154）却在 resource-mapping.md:551 只留颜色与 radius 34dp，均判「错」，是链上最 | | | | | | | |
| MemberCenterPage.ets | 7/6 | 5 / 2 | False | 4/5 | 3/4 | control | control | 4 |
|   | 进入点: A 定在修复轮 fixer-r1 那次写(照抄 private static 到跨 struct 调用点，直接引出 10505001)；B 定在生成轮 slice8-pay(:264 把含「/天」后缀的整串灌进注释仍写「rollingTextView 数字」的 30vp 槽位，而同一 agent 半小时前 :24 已读 | | | | | | | |
| SplashPage.ets | 8/6 | 5 / 4 | False | 4/5 | 3/5 | control | control | 5 |
|   | 进入点: 不同:A 进入点在环5(基线提取那版写 meta.json 时丢掉 theme/windowFullscreen,判错),B 在环3(conv-splash 首建 SplashPage 时两条现成指针都没打开,判错;脚本与技能按口径判缺,排其后)。B 更站得住:一是 A 自己在环4 写明「meta.json 第 21  | | | | | | | |
