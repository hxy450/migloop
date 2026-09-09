# V11 真实运行页面复核：展示保真不等于归因正确

同冻结源 `cb3682f` 读取原始调查产物，既不补调查步骤，也不替模型改结论。浏览器用真实鼠标/抽屉/原文入口，比较模型原始YAML与页面reason/basis/event文本，再比每个事件展开的真实输入/输出。截图是现场结果，不是mock。

## C3 rep1

- [实际页面截图](../2026-09-09-trace-fidelity/screenshots/v11-c3-rep1-real.png)。45步中6次版本查询，2次成功打开、4次被拒；图中5个精确版本实体，2次搜索导航转移，未把搜索变成读写边。
- 8条事件声明、8份原文输入输出逐字对账；没有basis就明确记录缺失，不编一份。
- 最后一次check为45，绑定匹配；UI不把mechanical_clear当语义正确。
- 展开前后trajectory SHA256都为 `2572fd6d353443509ecd8993be4272a1d1cd251dc6200726c0089e22ff089278`，无JS异常。

## Splash rep1

- [实际页面截图](../2026-09-09-trace-fidelity/screenshots/v11-splash-rep1-real.png)。8个图实体、7次版本访问、6次导航转移保持不变。
- 红色 Slice11@v37 的reason与双方basis逐字等于模型原稿。**该进入点本身被独立语义审查判为错绑；这里通过的是“页面没有篡改模型主张”，不是归因通过。**
- 3条事件声明都核回真实原文并展开输入/输出；3次check原始返回可看，最后一次为37。没有给老check补不存在的诊断字段。
- 展开前后trajectory SHA256都为 `d5356473c8d7f098c16b9d397132995be81e29cdf6512dc33e626ed35610ef2b`，无JS异常。

复查脚本：`tests/browser/probe_basis_smoke.cjs`，接受loopback页面URL和一个新的截图目标。语义裁决另见V11两组adjudication文件；红色只表示模型归因主张，引用位置可核并不保证原文支持断言。
