# 独立事件内核：当前状态与首版记录

## 当前状态（2026-09-12 持续迭代）

**未通过归因验收，不切换旧默认入口。** 原有三次迁移、十个文件、28项核心固定；raw不重跑。每次Luna独立调查，原稿/耗时/宿主可见性全保留，不挑最好的复跑。

统一入口：[固定评测约定](../file-first-10/evaluation-contract.md)，含文件/时间/有界答案、两种覆盖率、固定raw、成本和待实现的结论证据链验收。i20实际调用统计：[MCP与raw使用量](i20-tool-usage.json)。

| 冻结候选 | 范围 / 深度 | 核心正确 | 是否可交付 |
| --- | --- | --- | --- |
| [i05](i05-scores.json) | 10文件 / medium | 20/28 | 否，仍有重大额外错误 |
| [i07](i07-scores.json) | 10文件 / medium | 15/28 | 否，回归；另有一次交付hash不匹配 |
| [i08](i08-scores.json) | 2难例 / medium | 6/11 | 否，返修helper被错归初版 |
| [i09](i09-scores.json) | 2难例 / medium | 7/11 | 否，helper责任仍错 |
| [i09-high](i09-high-scores.json) | 10文件 / high | 24/28（85.7%） | 否，另有至少5项已核重大错误 |
| [i10-high](i10-high-scores.json) | 单跑Splash / high | 4/5 | 进度条追回；早期返回处理历史仍缺 |
| [i11-high](i11-high-scores.json) | Splash、Dice Index / high | 8/10 | 返回历史仍缺，日志又被错归初版 |
| [i12-high](i12-high-scores.json) | 同两题 / high，仅改GUIDE | 8/10 | 无该轮已核核心错归，但仍缺两段历史 |
| [i13-high](i13-high-scores.json) | 同两题 / high，原生增删清单 | 8/10 | 两段历史仍缺，另有主题输入误判 |
| [i14-high](i14-high-scores.json) | 10文件 / high，证据对账与工具返回渠道 | 27/28（96.4%） | 否；1项重大额外错误、1份图未完全接回 |
| [i15-high](i15-high-pilot-scores.json) | Member、CC Entry / high | 7/8（87.5%） | 否；Entry在本次调查内纠正构建结论，Member回归且有额外无据管线归因 |
| [i16-high](i16-high-pilot-scores.json) | Member、Splash / high | 9/11（81.8%） | 否；Member漏蒙层、Splash少早期返回历史且误称最后编译失败 |
| [i17-high](i17-high-pilot-scores.json) | Member、Splash / high | 9/11 | 否，输入未完整送达且有错误目标的读回引用 |
| [i18-high](i18-high-pilot-scores.json) | Member / high | 5/6 | 否，实际输入记录仍在未续读的正文后部 |
| [i19-high](i19-high-pilot-scores.json) | Member / high | 5/6 | 否，输入入口已送达，但打开时刻早于返回导致失败 |
| [i20-high](i20-high-scores.json) | 10文件 / high | 27/28（96.4%） | 否，Splash早期历史部分完成，Entry另有后修行为验证的错误否定 |
| [i21-high](i21-high-pilot-scores.json) | CC Entry、Dice Entry / high | 4/4 | 否，跨actor查询可达，但真实登录回执未送到已读片段 |
| [i22-high](i22-high-pilot-scores.json) | 同两题 / high | 4/4 | 否，CC未恢复行为证据，Dice把实测重入与未知桥键混为一谈 |
| [i23-high](i23-high-pilot-scores.json) | 同两题 / high，仅改GUIDE | 4/4 | 否，CC恢复真实HMOS登录观察，Dice仍错误否定已观测重入 |

[i24-xhigh](i24-xhigh-plan.md)的Dice Entry单跑已结束，最终原稿21f75603fb4c476d，尚待语义裁决，未启动下一份。实际Luna/xhigh已核，耗时1,073.95秒、总token6,397,399；mechanical valid不是归因已通过。相同i23代码/指南/题目，仅改变思考深度，代码、driver及10题prompt哈希一致。通过既定门槛才跑CC Entry，再决定是否覆盖余八文件。不是新工具改动，也不能用两题成绩代替十文件验收；不覆盖历史。

这些是开发者对冻结核心和原始证据的核验，不是独立盲评。泛化未证。字段/引用/历史边机械valid不是语义正确率。high若有收益，单列模型深度变化，不归功于工具结构。

i11新内核另对i09-high十份原稿重核：原稿全不变，十份仍可机械核回，历史边数量不变；只修正可兼容端点的选择，不把“更严格核验”偷换成修改答案或多造边。

最新完整十文件轮为i20-high：CC0723 16/17、DiceRoller 9/9、Codex 2/2。核心27/28，9/10文件核心全对，8/10文件同时满足核心全对且无已核重大额外错误。总输入输出46,281,905 token（其中43,748,608为缓存输入），模型累计6,035.7秒；比i14整轮更贵更慢，不能宣布省于raw。固定raw与工具仍有思考深度和Member题干差异，不把直接分数差当工具的纯因果收益。四例稳定性复跑尚未做。

工程侧：180项inquiry回归及Ruff通过。MCP/HTTP共用查询内核；正文、请求/回执上下文、时间范围、批量续帧和模型实际交付分别可核。i22增加同范围全池返回搜索、匹配actor分布及收窄入口；新增反向配对索引使一个真实查询10.35→2.21秒，完整结果一致，见[i22预检](i22-preflight.md)。这些局部速度和机器校验不认证归因正确，也不证明模型端到端更省。

i14新增工具返回输入渠道及结论事实对账，浏览器实测通过（`C:/Users/hongy/projects/_migloop-scratch/inquiry-i14-ui-smoke2`），原稿和实际轨迹不被手动查看改写；这是旧i13报告重核的工程检查，不计新模型成绩。独立临时8879测试服务已停止。人工评审的错actor与颠倒日志引用已撤回，详见[评审更正](i14-adjudication-corrections.md)，核心标准与分数未变；不能把撤回扣分说成工具修好了模型。

当前预览（服务运行时可用）：http://127.0.0.1:8878/?report=739132fdf2f14e5d 。展示i20-high真实Member原稿及实际轨迹，使用独立预览数据库，不改冻结实验数据库。该例核心6/6，仍有属性措辞及分组actor提示等审计限制。相同finding、节点身份和完整时间区间可合框，框内原因/角色分别保留；不补不存在的边。最新浏览器产物：`C:/Users/hongy/projects/_migloop-scratch/inquiry-i22-groups-ui-final`。原因、原文、每条既有边、搜索分组和手动探索不改模型轨迹均已检查；不是全稿语义认证。旧报告与截图保留。

运行产物根目录：`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/inquiry-iterations-20260911`。验收门槛见 [iteration-plan.md](iteration-plan.md)。

## 以下为首版工程交付的历史记录

日期：2026-09-11。规范见 [inquiry-core.md](../../specs/inquiry-core.md)。分支 `dev/inquiry-core`，旧实现基线 `b7061d2`。

后续单次Luna验收已完成：[结果与失败定位](luna-results.md)。严格正确3/6，持平固定raw；token和时间没有优势，结论图未达标。下文的“0次模型运行”特指最初工程交付阶段，不包含这次后续验收。

## 交付状态

这是新内核的可运行第一版，不是旧功能全量等价替代，也不是已经证明超过原始组。

- 新内核不导入旧 atoms/filestory/probe/verdict/service；原有默认CLI、页面、用户的DevEco修改未变。
- 统一Source/Record/原生Operation，持久化SQLite索引，file/agent为时间范围视图。
- 一个查询约定，批量自由调查；MCP只暴露 investigate/page/submit。HTTP和MCP调用同一个Engine。
- 原生读写、独立Codex补丁回执、可核原生子代理派发；未知脚本保留相关原文，不做通用脚本解释器。
- 原始引用核字节；多源同call_id不拼接，迟到结果不冒充早期输入。
- 完整选定正文保存并可续帧；服务端发出与宿主实际可见分开记。未接宿主观察的轨迹必须显示未核可见性。
- 一种inquiry/1结论格式，原稿保存，节点原因、引用、历史边分别处理。读取保存报告时重核证据，不复用失效的绿边。
- 最小SVG证据图、节点原因、原文展开和查询日志；手动查询不冒充模型调用。错误边不绘制。

明确未带入：旧版v/via查询、多代报告兼容、完整磁盘状态重放、可认证的逐行blame、任意脚本的读写效应推断。blame目前明确返回未证及操作入口，不能把它当已实现旧版来源能力。

## 验证

新内核32项测试通过；连同旧HTTP/单调查员边界回归共83 passed、2 skipped。不是全仓测试重跑。Ruff检查通过。

真实Chrome验收五项通过：载入3节点/2条可核边、显示节点原因、手动查询不改轨迹、原文展开、故意写错的边不绘制。第一次暴露了带`?report=`的首页路由未识别，已修并加HTTP回归。截图是人工取证样例，不能冒充Luna调查。

样例地址（仅在预览服务运行时）：

```text
http://127.0.0.1:8878/?report=26e5b8473c82467a
```

截图与浏览器验收：`C:/Users/hongy/projects/_migloop-scratch/inquiry-browser-20260911-final`。

真实会员页：290登记源、33,735条物理记录、3,436条原生索引效应。已核到Slice8生成期实际输入/输出、mask脚本103→104、图片脚本233→234、编译报错24与成功回执37。脚本可读不代表机器已认证其目标文件效应；本次是已知位置的可取证性检查，不计准确率。

真实Codex：直接导入用户提供的2026-08-16/08-21两份AIPPT rollout，共16,033条记录、205条成功原生patch_apply_end效应。普通shell读写仍不是自动认证关系。

## 数据与成本

产物均在工作区外的scratch，不进入源码包：

- `inquiry-member-20260911.sqlite`：约310MB；索引包含可全文检索的原文投影，不复制整个工程。
- `inquiry-codex-20260911.sqlite`：约41MB。
- `inquiry-member-acceptance.json`：无模型真实取证验收。
- `inquiry-member-acceptance-final.json`：最后两个引用/路径边界修改后的复核，仍为3节点/2条可核边。

第一次试建存了两份搜索正文与重复操作payload，生成了约613MB索引；该**本轮自行生成的临时索引**已删除并重建。原始转录未删、未改；索引可从原池再生成。

会员池当前导入约21.09秒，Codex约2.32秒；导入只做一次，不是每次查询。最终人工复核单次测得会员生成关系查询约0.002秒、修复窗口记录查询约0.057秒。主机负载、缓存未受控，不能与旧模型端到端耗时作因果比较。

**本轮模型运行数为0。未重跑raw，未改固定评分，未证明准确率、token或端到端时间优于raw。**

## 运行

使用安装了项目inquiry可选依赖的Python；开发环境也可设`PYTHONPATH=src`。

```text
python -m migloop.inquiry --db <新的索引.sqlite> import --pool <原始材料池>
python -m migloop.inquiry --db <索引.sqlite> mcp
python -m migloop.inquiry --db <索引.sqlite> serve --port 8878
```

导入不覆盖已有索引。CLI query接JSON查询；完整JSON输出仅供工程核对，模型应走有明确续帧的MCP文本。

## 首版当时的下一步（已执行，当前迭代见页首）

冻结这版代码与同题任务后，让Luna在会员页跑一次，保持原始读取能力，使用新MCP，核最终宿主交付及原因。原始组不重跑，不加入新的skill或题目。明确报告正确项、额外归责错误、可见性、成本；不因代码更少或查询更快宣布成功。

如果仍不达标，记录具体缺失证据/推断错误，不能立刻再发明下一代协议。是否切换默认入口和删除旧返修实现，由这次验收而非代码行数决定。
