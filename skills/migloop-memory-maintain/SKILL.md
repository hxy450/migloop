---
name: migloop-memory-maintain
description: 将新增、修订或撤回的迁移情景卡融入已有经验库，提炼有适用条件和来源的短经验，维护目录及版本依赖。
---

# 把卡片提炼成经验

输入指定经验库与卡片，输出经验库新版本和变更说明。经验保留 when、unless、why、how、check；证据树留在来源卡中。

1. **读取版本并入卡。** 已有库运行 snapshot，新库运行 init。用 ingest 导入卡，或用 withdraw 撤回整卡/指定结论，再读取新的 revision。
2. **比较已有经验。** 用相邻 recall 的 search/read/browse 加 `--all-statuses` 查相关条目。比较适用条件、偏差机制与预防动作：相同则补证，不同则分支，条件内冲突则保留争议。
3. **写提案。** 按 [维护格式与命令](references/protocol.md) 填写短经验，绑定真实 `case + claim + revision`；实际依赖的其他经验列 requires。目录负责导航，每条经验保持一个稳定身份。
4. **审核并发布。** 核对来源是否支持条件和建议，审核完成的标 active，待补的留 candidate，冲突的标 disputed。用 apply 发布；版本冲突时重读并比较变化，重新形成提案。

来源修改或撤回后，检查 impact 给出的受影响条目，复核后再恢复使用。语义审核由本维护任务完成，机械检查负责引用、版本和依赖。

交付新 revision、主要归并理由、更新/退役范围及待复查项。命令在本 skill 目录执行，完整用法按需读取协议。云端发布和 hook 接入由宿主负责。
