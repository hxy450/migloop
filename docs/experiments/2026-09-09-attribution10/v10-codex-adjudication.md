# V10 Codex 独立语义裁决

状态：四文件rep1的裁决已落盘；四份rep2调查也已完成，但独立裁决尚未补齐。评审因额度中断，见[检查点](2026-09-10-checkpoint.md)。裁决对象是最终reference双哈希绑定的`verdict.yaml`；机械check不认证语义，不因耗时或成本印象调整语义分级。

## C3 rep1

核心接受，完整注释有一项可恢复遗漏。稿件正确保留 competing hypotheses：Monitor/visibility 方向只有 reviewer wrong_edit 反证主张，独立/条件挂载方向只有 fixer、summary 和主会话主张；没有目标源码 diff，也没有修后 fresh capture，不能确认真实根因或结果。

它比 V9 C3 rep1 更好地恢复了生成前要求：六步引导、末页 5 秒进度到 100% 后进入首页；但仍未明确核到 reference 所列的 GuideInit Kotlin/layout/snapshot 输入，也未交代生成报告曾声称 5110ms 进度流已实现，因此 fact 1 只记 partial。low-confidence/still-open、Round 1 reviewer、Round 2 独立挂载和最终 fresh-capture 债均有覆盖。

V2 结构没有制造事实：target 只作声明路径匹配而没有 file version；六个 event 均定位真实 owner/seq，四个 inbox 事件标为 `textual_only=true`，所有 event 的 `effect_version` 都为 null，也没有创建节点或边。

交付成功：submission 为最终 checked-draft reference，`verdict_ok=true`、`coverage_complete=true`。指标为 input total 840,519（其中 cache read 764,416、uncached 76,103），output 8,229，37 calls，tool-return 119,420 chars，wall 193.375s，end-to-end 196.131s。这里只记录逐次事实，不以较低时间或字符量推断语义改善原因。

## C2 rep1

核心接受。稿件用 F005/F006、AppEvents 定义和 close_batch 自述恢复了修改前的 insert/event 要求与背景；对真正争点处理正确：fixer 摘要称生成改经 WorksService，reviewer 随后称同 DAO、同事件而判 wrong_edit，但目标文件没有可核版本或 diff，两者都不能升级为源码事实，作品未呈现的真实断点仍未知。

完整层有两项遗漏：没有明确恢复“PptRecordRepository 是唯一 post-insert CREATED publisher”的历史执行摘要，只用近似的 close_batch 主张覆盖；没有提 Round 2 Works canonical 被系统联系人污染。target 未定位到文件版本；三个 event 均定位真实 owner/seq，E3 是写 reviewer flag 到 summary 的报告写入，不是产品源码 patch。最终 submission 可交付但 `coverage_complete=false`，与语义核心分开。

交付指标：input total 1,454,351（cache read 1,364,480；uncached 89,871），output 12,149，47 calls，tool-return 135,197 chars，wall 284.411s，end-to-end 287.208s。单次指标不作语义质量或总体成本因果判断。

## C1 rep1

核心与完整注释均接受。稿件直接引用 closer 的 BLOCKED、补丁前读回、真实 patch、修后 PASS 与 `build_run=false`，并准确指出“必须父传”的当时自述被实际仍保留 no-op 默认函数的补丁推翻。三条 reference fact 均 supported；没有把静态门通过写成编译或设备行为通过。

target 与三个 event 均定位真实 owner/seq；只有 patch 获得真实效应版本，closer PASS 正确标为文本消息，不造文件版本或边。指标：input total 842,508（cache read 757,248；uncached 85,260），output 12,260，44 calls，tool-return 134,360 chars，wall 265.813s，end-to-end 268.650s。

## C4 rep1

核心接受，完整层有两项遗漏。稿件完整恢复 Block→Default 的写前源码、SDK Default 语义、原生 patch/读回、同轮构建受阻与旧 HAP 边界，并明确后置 manifest 的同意转场不能绑定为本补丁因果或完整专项回归。

它没有枚举源码中的四个 Event 名称，因此 fact 1 为 partial；也完全遗漏后续原生 `BUILD SUCCESSFUL` 与 `HAP installed`，因此 fact 5 omitted。保存的回放 manifest 可作后置行为记录，但不能替代 native build/install 事实。五个 event 均定位真实 owner/seq，只有 patch 具真实 effect version，尾后事件未造节点/边。

指标：input total 932,200（cache read 846,336；uncached 85,864），output 13,821，60 calls，tool-return 129,569 chars，wall 300.226s，end-to-end 302.913s。
