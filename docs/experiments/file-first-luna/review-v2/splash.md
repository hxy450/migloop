# SplashPage.ets 证据底稿

生成边界2026-07-24T22:16:20.102Z，截止2026-07-26T21:48:57.793Z。调查的是该文件的实际变化，后期发现的多个现象不自动各算一个预设缺陷。

## 1. 已核修改事件

| 事件 | fixer调用→返回 | 修改事实 | 原因和未认证部分 |
|---|---|---|---|
| 01 | L103→104 | 批量mask脚本报告Splash一处替换，增加Palette依赖 | 遮罩契约补齐；51处是全池总数，不是Splash数量 |
| 02 | L233→234 | `icon_splash_app_name`补width185/height125，保留Contain | 固有尺寸换算来自修复者，未独立认证所有像素 |
| 03 | L346→347 | 添加onWillDismiss处理；同次给Progress加strokeWidth13和enableScanEffect:false | 返回门禁和绘制厚度是同次操作里的不同意图；不是一个事件只能有一个原因 |
| 04 | L352→353 | onNavBarStateChange中在重新可见且privacyDialogVisible时恢复弹窗 | 从协议页返回的兜底，不能代替“消费BACK关闭请求”本身 |
| 05 | L485→486 | 新增系统栏辅助逻辑、进入隐藏和离开恢复 | 修复者依据主题与生命周期解释；不是独立设备重放 |
| 06 | L488→489 | onRoute跳Guide/Home前恢复系统栏 | Navigation压入子页面时不只依赖宿主销毁的修复意图 |

原文：[fixer](/C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/splash/pool/ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-a68daf720e780b4c2.jsonl:346)。完整调用及返回：[change-events.json中的splash:01—06](/C:/Users/hongy/projects/_migloop-eval-20260909/file-first-luna/review-v2-final/change-events.json)。

## 2. 返回处理的历史：哪些事实真正成立

1. converter L71的初版Write含`.onBackPressed(() => true)`。
2. entry-setup L123的Edit旧侧含该行，新侧没有该处理，改为Navigation装配和API限制的注释；L124报告成功。
3. Slice11 L236的后续Edit新侧包含isModal相关解释；这能定位解释的作者与阶段，不能把注释当API保证。
4. 后期验证者报告BACK关闭隐私弹窗/白屏；fixer L346添加onWillDismiss，L352另加恢复兜底。

原文：[初版](/C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/splash/pool/9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aconv-splash-9d5902d803bbcde6.jsonl:71)、[装配Edit](/C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/splash/pool/9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aentry-setup-07108f5df45c357c.jsonl:123)、[Slice11解释](/C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/splash/pool/9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aslice11-startup-50a0622bcfe4a588.jsonl:236)。

有依据的结论：原有返回处理在装配中被移除，后续实现/解释没有形成足够的返回门禁保障；最终报告的现象不能倒推为初版作者已被证实制造。

必须收紧的旧说法：**初版“存在处理”不等于初版“所有弹窗BACK场景已做对”**。没有用设备重放证明初版覆盖了首弹窗、挽留态、协议页返回等所有场景。也不能只凭删除一行证明它是最终白屏的唯一充分原因。

D-020只接受某些外壳返回差异，不自动等价于“允许隐私弹窗绕过”；但要定为skill/编排缺陷，还应核完整决策的适用范围，而不能只比较几句摘要。

## 3. 其它变化的生成责任边界

- 进度：初版已有Progress和height13；后修补绘制条厚，不能写成原生成没实现业务进度。
- 系统栏：生成前主会话L404已读到windowFullscreen信息。这排除“全池直到后期才出现要求”，但不证明该细节已经传给页面作者。页面生成输入的沉浸式/安全区描述也不自动等同于隐藏/恢复系统栏全部契约。
- 图片、遮罩：实际后修可核；特定上游规则是谁遗漏，现有底稿不指定唯一答案。
- 路由大小写：后期WorksComponent调用修正，不列为Splash文件的新修改。

## 4. 各方分歧复核

| 主张 | 原始证据 | 裁决 |
|---|---|---|
| raw第一次：同名子目录为空、没有完整补丁 | 冻结池146个JSONL；具体子代理内有上述调用和结果 | 不成立。其查询没有正确交付子代理内容，详见调查诊断 |
| raw第二次：具体BACK API和mask补丁未知 | fixer L103/L346，结果L104/L347 | 是未查到，不是允许材料中没有 |
| tools第一次：初版处理与后期弹窗组合失效，进入点在初版converter | 初版→装配Edit→Slice11记录 | 现有证据不足以支持这一具体初版归责；不能用后期finding直接跨过中间变化 |
| onNavBarStateChange修复就是BACK门禁修复 | L346和L352不同操作 | 必须区分关闭拦截与返回恢复，不因为报告合并叙述而丢掉实际差异 |
| 所有修复已设备闭环 | 已有编译成功、修复者报告 | 不足；缺相应独立设备复验。历史报告的复现属于已记录参与者结果 |

工具第二次提交引用损坏，无有效最终YAML；这是交付失败，不能将草稿六项一律判为语义错误。

## 5. 底稿仍不能保证什么

6次是已登记/复核事件，不是所有不透明写已穷尽。不存在独立完整设备重放或独立审阅者对整条因果链的认证。可以用这组证据反驳“初版没有任何返回处理”和“没有子代理补丁”，但不能强行构造一个唯一skill根因。
