# 新事件内核：单次 Luna 验收（运行前冻结）

2026-09-11。候选产品提交 `11c536c`，只复制 inquiry 包和无副作用的父包初始化文件。不切换现有默认入口。

## 条件

一份 MemberCenterPage.ets 文件，原始池、生成/观察截止、任务原文沿用 longchain-20260911 的固定实验。模型 gpt-5.6-luna，medium，最多1800秒；保留只读 shell，新增独立 inquiry MCP。继承固定 raw 全部其余设置，不启用新 skill、网络或第二调查员。MCP完整通用 GUIDE 附入 prompt，避免依赖宿主是否传递服务说明；这是操作条件变化，不宣称只有数据结构这一个变量。

原始组不重跑。只调用一次模型，不自动修复格式，不自动补跑；调查员自己可使用 submit 诊断继续补查。运行器不加答案提示，不改原稿。原始池以内容哈希前后核验；新索引从原池重建，不复制人工样例、查询、结论。stdio预检只初始化和列工具，不查数据、不调用模型。

参考答案、旧报告、代码和评测目录在原始池外，禁止调查员读取。只读 sandbox 不是禁止所有池外读取的充分证明，另核实际 shell 命令。索引路径作为MCP参数可见不等于有意隐藏，不能声称强隔离或盲评。

## 固定判据

沿用此前冻结的 reference-units.json / scoring-core.json 中 F10-01，不在看到输出后调分母。以下是审阅者摘要，不交调查员：

| 单位 | 严格正确所需事实与边界 |
|---|---|
| mask | 三处对话框按类型补 mask；AppLoad透明、另两处Palette，H5原来已有透明；更早唯一原因未证 |
| images | 两处挽留图片补比例/高度与padding约束；不能仅据补丁宣称视觉验证成功 |
| cta | 宽度+margin改外层padding；保留高度、点击、动画，不是没改 |
| price | 统一字号改分段且中间方案再改；Slice8已收到相关源码仍写出统一字号；不能把后期写者直接定为首因 |
| indicator | 增调颜色/位置；缺失精确值的早期输入和唯一责任人未证，spec不明写左下颜色 |
| repair-compile | 后修引入private助手，跨struct编译报错、去private后构建成功；不是初版生成问题，不证明视觉正确 |

允许按原因合并或拆分，语义匹配；correct/partial/wrong/omitted。严格得分只计correct，固定 raw 为3/6。另列额外错误因果主张，不能用局部覆盖掩盖错误归责。这是一个文件六个单位，非六文件/总体ACC；开发者核原文，不是独立盲评。

## 交付与成本

保留原生录制、原稿、submit结果和查询帧。核最终report_id/hash是否来自同次调查员的实际submit；UI原样显示其原因，仅画有依据的历史边。引用与边核验不等于语义正确。

逐帧对照原生exec/wait的模型可见输出，不能以MCP内部返回代替；若需要解封装，只允许实际输出里的合法JSON内容，不用服务端内容补洞。分别报告记录分页、结果帧是否取全、宿主截断/不可证完整。

报告模型累计input、cached/uncached input、output（不重复算reasoning）、total以及耗时。一次索引导入单列；后处理无模型、计时。与固定raw比较，但n=1、缓存/主机负载不受控，不作泛化或计费金额推论。若不达标，具体区分缺证据、未交付、没查与错误推理；不在本次验收中立刻改候选或再试一遍。

启动方式参考：[Codex非交互运行](https://learn.chatgpt.com/docs/non-interactive-mode)、[MCP配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、[Luna模型说明](https://developers.openai.com/api/docs/models/gpt-5.6-luna)。实际采用本地已验证的同一原始组CLI启动器，不改全局配置或认证。
