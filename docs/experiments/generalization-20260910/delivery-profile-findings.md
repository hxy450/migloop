# 离线性能定位：selection、budget fit 与 native postprocess

结论：在本次 Dice 开发样本上，不能把查询或后处理慢归因于 budget fit 的 deepcopy/JSON。24页 changes 重放的 selection 占45.365秒，48次fit合计0.076秒；实际热点是每页重复原生源索引扫描、缓存未命中和保留对象大小计量。有效身份的冻结v3后处理中fit调用为0，同一changes索引路径占结论绑定的大头。

本审阅只读取既有开发轨迹及报告，无新调查模型、无新留出答案、无历史shell执行，无src或冻结包修改。这不是端到端模型提速结果。

## 产物与复现

脚本：[profile_delivery.py](profile_delivery.py)。

新审计目录：C:/Users/hongy/projects/_migloop-eval-20260909/generalization-20260910/delivery-profile-1

包含replay、selection、cache、postprocess、postprocess-bound、postprocess-snapshot、postprocess-frozen-bound各自result.json、cProfile二进制和可读profile JSON；另有显式runtime snapshot。后处理只序列化到内存测量，未覆盖正式run的verdict/query-trace。

所有模式独立新进程、顺序运行。代表性命令如下；out必须为尚不存在的新目录：

~~~powershell
& 'C:/Users/hongy/projects/migbot-elite/.venv/Scripts/python.exe' -B -X utf8 docs/experiments/generalization-20260910/profile_delivery.py --repo C:/Users/hongy/projects/_migloop-eval-20260909/generalization-20260910/delivery-profile-1/snapshot --eval C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10 --out C:/Users/hongy/projects/_migloop-eval-20260909/generalization-20260910/delivery-profile-next/cache --mode cache
~~~

模式replay为三种查询分段计时，selection为单changes重复和profile，cache只观察缓存返回状态；postprocess另可指定 --postprocess-case F10-07 --postprocess-rep 2。要复核正式v3有效身份路径，repo必须改为file-first-10/tools-v3/code；不能用改过的live包复核旧ledger身份并把短路误作提速。

首轮脚本版本的完整字节已另存于审计目录：

- profile-script-initial.py：SHA-256 1a775f804878ede6acc686c06c1c41b32c22e5d12351b6dd7fe582df7ff92cfe，对应replay/postprocess。
- profile-script-selection.py：SHA-256 4d2d6adf2a5b48ca437af0a9933e0ea8c12336864e54089c089f6f593b972599，对应selection/postprocess-bound。
- 后续cache/postprocess-snapshot/postprocess-frozen-bound各保存实际profile-script.py；result.json绑定其SHA。早期版本按本轮扩展前内容重建并核对SHA完全匹配，非猜测的近似副本。

## 样本、计量与版本界限

1. 24子项、30000字符预算来自既有tools-v3-atom-overview-audit/20260910T164423Z/F10-03/request.json。它是v3开发审计对旧v2开发trace step16的重放，不是声称正式v3调查员发过此24项调用。24项均为同一文件/时间范围、不同页的changes。
2. 单agent由正式v3 F10-07 rep1 step8 item5的请求派生，仅改view=overview、limit=40、details=false；actor和时间不变。这是明确的离线代表负载，不冒充原调用。
3. 大expand为正式v3 F10-07 rep1 step18 item1，保留原ref、scope、max_chars=12000，外层单项batch预算6000。原始长记录只读，不执行其中命令。
4. selection计实际investigation.query，fit计实际delivery_budget.fit；重复fit时只用捕获的相同selection对象，五次未profile结果及一次profile结果均与原投影digest一致，输入digest未变。计时不包含循环后的校验digest。profile是另外一轮，不能用其墙钟代替未profile耗时。
5. render分开计batch JSON、receipt digest/附加与MCP JSON封装。封装大小不是最终模型上下文；没有测网络、token化、服务排队、推理或exec外层截断。
6. “冷”只表示新Python进程的应用缓存，未清Windows文件系统缓存，不能称物理冷盘。

18:33:44–18:36:05的前三轮live进程内部package hash均稳定，temporal_atom为472280c0f4182bb4171e546f642825fcc79a21773c8427c15a50bcb2ca0ab73f。随后父端把消息预览从240改到4096；18:36:43之后的live/snapshot为74e277e98924b610b28b2dab3af70bf4f93100effe2275ce9244c5841e122db7。每个进程内部稳定，但跨进程是两个版本，不能合并成同一实现的before/after。

后续cache测量使用新显式snapshot；后处理完整绑定测量使用正式冻结v3。cache热点模块raw_events.py在这两个包字节相同，SHA为bb67cb7b03cbdf8acb27d98886f464bffac4a76610f393babffedbebf8d84bc7；delivery_budget.py亦相同，SHA为9ab650ca27365e641d5ddeaed3ce4b6b81e82adf7117f5f00c1af3f5cc803972。atoms/change_inventory/temporal_atom存在版本差异，不以此做总体包等价声明。完整package文件表在每个result.json中。

## 查询实测

单位为秒，表内均为未profile计时。单agent/expand在同一replay进程内晚于24项负载，因此是热环境数据。

| 负载 | selection | fit合计 | fit调用 | cached selection后五次fit中位 | 实际batch |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dice24小预算 | 45.36464 | 0.07641 | 48 | 0.07656 | 45.44152 |
| 单agent overview | 0.03963 | 0.00593 | 2 | 0.00597 | 0.04564 |
| 大expand | 0.01590 | 0.00095 | 1 | 0.00084 | 0.01690 |

首轮新进程建账为2.37844秒，另外几轮约2.366–2.417秒。Dice24的24次selection均约1.837–1.948秒，没有只有第一页慢、后续页快的现象。fit约占该batch墙钟0.17%；即使完全消除这部分，也无法解释45秒级主体。

另起新进程对单changes进行三次未profile取数：1.89592、1.88059、1.90159秒，中位1.89592秒。复现了每页稳定重复成本。

### fit内部确有deepcopy热点，但不是本负载总热点

缓存selection后的一次cProfile：

- Dice24：48次fit、303780次deepcopy调用，fit累计0.367秒，deepcopy累计0.338秒；对应未profile中位仅0.07656秒。
- 单overview：2次fit、19064次deepcopy调用；未profile约0.00597秒。
- expand：1次fit、1575次deepcopy调用；未profile约0.00084秒。

递归调用数和累计时间有包含关系，不能相加。cProfile对这类Python调用密集路径显著增时。结论只是“deepcopy是fit内部优化候选”，不是“它导致每次查询或postprocess慢”。

## selection热点与缓存证据

单changes的一次cProfile墙钟4.616秒（不同于未profile约1.896秒）：

| 函数 | 调用 | 累计秒 |
| --- | ---: | ---: |
| change_inventory.build | 1 | 4.601 |
| raw_events._scan | 3 | 3.875 |
| raw_events._source_index | 240 | 3.788 |
| raw_events._retained_size | 240 | 2.259 |
| json.loads | 29530 | 0.386 |

再次用显式snapshot只观察真实_source_index返回状态，不修改缓存预算、不复用伪结果：

| 同请求重复 | 查询秒 | miss | oversize_not_cached | hit | 结束缓存 |
| --- | ---: | ---: | ---: | ---: | --- |
| 0 | 1.92231 | 237 | 3 | 0 | 31源，29508565 bytes |
| 1 | 1.89457 | 237 | 3 | 0 | 31源，29508565 bytes |

缓存全局预算32MiB、单源上限8MiB。单changes内部3次扫描80源；索引访问逐一保存于cache/result.json。扫描工作集超过缓存容量时，顺序扫描持续驱逐，下一轮又重新构建并重新做_retained_size；重复请求没有实际命中。这是已复现的循环扫描缓存抖动，不是仅凭源码猜测。三个oversize状态是三次扫描的源访问计数，不能写成三个不同超大源。

值得优先研究的落点是同一查询内共享原生扫描结果、同一有界库存的翻页复用以及避免顺序全扫描破坏有用缓存；本轮没有实施。任何后续缓存方案必须保持registry/signature失效、内存上限、截点及晚结果语义，不能通过不检查源变化或永久缓存整个池换速度。仅增大缓存预算也未在本轮验证。

## 字符量与序列化

| 负载 | selection合计字符 | fit后data字符 | batch JSON字符 | 带receipt的MCP封装字符 |
| --- | ---: | ---: | ---: | ---: |
| Dice24 | 1253263 | 28960 | 82913 | 90946 |
| 单overview | 20569 | 11455 | 14305 | 16304 |
| expand | 13092 | 6000 | 7490 | 8386 |

Dice24为4ok/20deferred；不是24项完整交付。data预算虽低于30000，但续读、错误/延后元数据、请求与回执等使batch正文超过82000字符。其JSON渲染约0.00049秒、receipt hash约0.00041秒、MCP包装约0.00029秒；所以“文本很大”在本机主要是交付量/上下文风险，不是本次CPU序列化主耗时。不得把本地封装字符直接当调查模型实际输入token或据此判定全部内层结果未收到。

## Native记录后处理

正式v3 F10-07 rep2原始报告、原转录，使用原冻结包，identity_bound=true：

| 阶段 | 未profile秒 |
| --- | ---: |
| 新进程建账 | 2.41683 |
| 原生转录调用提取 | 0.00347 |
| trace身份核对 | 0.00213 |
| 文稿解析 | 0.01463 |
| verdict_v3.build | 2.43810 |
| query trace投影 | 0.00570 |
| 结果JSON序列化 | 0.00616 |

提取16个native调用（含8个exec、2个guide、5个batch、1个changes），而非把batch子项当独立outer调用计数。整条后处理及其额外profile中，delivery_budget.fit调用为0。

对build单独profile：5.874秒中，_changes累计4.688秒，raw_events._scan累计3.965秒，_retained_size累计2.340秒，仍是库存扫描路径。累计时间不可加总；绝对值以未profile表为准。原生转录提取/receipt核对在该样本仅毫秒级，不是2秒级主体。

短路反例不能混用：

- 当前包跑旧03 rep1：报告本身ledger有拼写差异；identity不绑定，build约0.00068秒。
- 当前live/snapshot跑旧07 rep2：原报告与当前包ledger身份不一致，build约0.00040–0.00044秒；正式冻结包对同一原报告能绑定。
- 以上短路结果全部保留，目录postprocess-bound名称只是当时拟测目标，实际result.identity_bound=false，不按目录名认定成功。没有为获得慢路径而修改原报告/trace或绕过身份门禁。

本脚本没有完整复制runner的目标字段检查、错误包装与落盘步骤；也不包括Python进程创建、MCP网络、调查推理或排队时间。因此不能把分段耗时总和直接说成正式run总耗时或声称重放使模型端到端更快。

## 绑定与范围限制

关键result.json SHA-256：

- replay：ab95f4fd251635669a562b4b028d6eebec454dbfa52d9a06d0d6f86ced93d194
- selection：4beba1b46d059f919b801bea0edea9b78828babeb09b023a96f929673a464287
- cache：e29666afc6694ab67270f56abd4af445c72e2f331425d1c6b57b5dbbb6069b7b
- postprocess-frozen-bound：f01627289d46edb6617de51c53ce719f3058a2ecf6c2abbbc43abe4d26a9214f

每份记录另绑定输入请求/trace/settings/旧报告哈希、Python版本、PID、开始/结束时间、80源的stat和运行前后代码哈希。未把stat对账说成重新验证全部原池字节；没有修改池文件。profile及计时均无并发自有诊断工作，所有自有短进程完成后退出。单开发池、少量负载不支持所有项目的性能结论，也不支持任何归因准确率或迁移收益结论。

## 后续候选：整池请求级scan复用的失败对照

父端实现请求内最多一份、128MiB上限的整池scan复用后，本审阅先固定reuse-snapshot，再允许live继续开发。这里只测试该固定候选，不把不同live版本混作收益。脚本为profile_scan_reuse.py；同快照、同请求、同脚本，关闭组唯一开关是进程内将_REQUEST_SCAN_BUDGET从134217728改为0，结束恢复原值；没有改源或永久缓存上限。

| 负载 | 关闭秒 | 开启秒 | 关闭/开启scan数 | 关闭/开启复用命中 | 开启保留量 |
| --- | ---: | ---: | --- | --- | --- |
| 单changes | 3.94004 | 4.93359 | 3 / 3 | 0 / 0 | 0 |
| 同24项 | 95.17459 | 126.62602 | 72 / 72 | 0 / 0 | 0 |

这次候选关闭组也比早期基线慢，不能拿早期45秒与新组直接算优化倍数。同候选的两次测量只是一对顺序运行，没有统计置信度；CPU时间也记录在result中。没有提速证据，反而观察到额外成本。

两组单页及24项的JSON树完全相等，甚至无需去除cache统计；请求、代码文件表、脚本SHA均相同。24项仍4ok/20deferred，data_chars=28960，不能把效能失败改写成语义/交付改善。两组请求正常返回后的ContextVar为None，捕获的请求状态字典都已清空。

容量核验使用独立profile_scan_capacity.py，仅做一次真实inventory、不上调上限：_retained_size在134217728上限处返回134217761，随即停止，计量约0.55584秒。这是“对象图超过上限”的下界，不是整图总大小。真实池没有保留、没有复用；重复超限计量与回退是新增成本来源。一个6005字节的小合成图则能命中，说明机制并非完全未接通，而是该真实池不满足入缓存条件。

两组独立合成检查均证实：改动仅发生于新audit目录内的fixture；源变化后不复用旧scan，旧raw ref被拒；正常和异常退出均释放请求状态。新材料可重新读到，不把“拒绝旧证据”说成禁止读取新源。没有修改任何正式池文件。

产物：reuse-off、reuse-on、reuse-capacity子目录。关闭组result SHA-256为e939026bff4a9ede382f1e19c5243954182e1d0614d568a2e8428bb13738d707；开启组为661ad127e84d588640786f0f26d6b4711ae5137f3b3a8120fe24eb64a485a586。两组时间分别为18:47:58–18:49:40Z与18:49:54–18:52:08Z。失败样本保留，不通过调高cap或换文稿隐藏。下一种按源复用方案尚未在这里验证。

### 按源容量补测（仅算术，不是新方案提速）

profile_source_capacity.py在同reuse-snapshot中逐源读取一次，以128MiB为每个对象图的有界计量上限，不修改原32MiB LRU/8MiB单源配置，不额外持有整个池的索引集合。source-capacity/result.json保存80条源级结果。

- 先前三个oversize访问去重后只有一个源：81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl，被每次查询的三次扫描各访问一次。文件9,876,117字节；其索引计量45,952,653字节，本次在测量上限内完整完成，不是下界。
- 80源索引逐项计量合计137,714,218字节，全部单项完整，约131.33MiB。该合计按缓存条目各自去重，不是跨源唯一对象堆或RSS；也不是此前整池_Event投影的完整对象大小。
- 原始排序下，128MiB只填不驱逐的纯算术模拟可容纳79源，计133,211,989字节，余1,005,739字节。未容纳的是efdc8b71-8d3f-40f6-a7e2-044748cf875b.jsonl，索引4,502,229字节。
- 该模拟没有实现缓存、没有计额外容器开销，也不保证实际新方案的命中或速度。父端下一候选须另冻结、另测；不替换已失败的整池方案结果。

## 按源请求缓存候选：同快照on/off与wire对照

新版固定于source-reuse-snapshot，使用profile_source_reuse.py；全程只运行此快照，不随父端live后续开发变化。开启/关闭两组的完整代码文件表、脚本SHA和请求SHA完全相同。关闭组只在进程内将_REQUEST_SCAN_BUDGET设为0，开启组维持134217728；32MiB全局LRU和8MiB全局单源上限不变。旧95/126秒整池方案的失败结果保留在上一节，未覆盖。

此处“单changes”为仅含一个changes子项的batch（30000预算），随后在同进程测24子项batch；它不是独立MCP标量调用的端到端计时。两组顺序及请求一致，编码/合成检查在查询计时之外。

### 性能与真实命中

| 负载 | off墙钟秒 | on墙钟秒 | off CPU秒 | on CPU秒 | on request_hit |
| --- | ---: | ---: | ---: | ---: | ---: |
| 单changes | 3.79297 | 2.03164 | 3.75000 | 2.00000 | 158 |
| 24项changes | 90.59976 | 23.76548 | 87.93750 | 22.76563 | 5609 |

24项selection为90.46807→23.59574秒，fit合计0.13070→0.13970秒，仍非fit主导；48次fit未减少。这个单次顺序对照中的离线batch约快3.81倍，不是统计置信度，也不是模型或系统端到端速度。两轮新进程建账分别2.94670与2.40027秒，未把它们计入表中查询耗时；操作系统文件缓存和外部系统负载未严格控制。

- off单页240次源索引访问：237 miss、3 oversize；off24项5760次：5688 miss、72 oversize，request_hit为0。
- on单页：79 miss、1 oversize、158 request_hit、2 global hit。on24项：79 miss、1 oversize、5609 request_hit、71 global hit。
- 请求内实际保留79源、1个skip guard。单页峰值133206824字节，24项峰值133205864字节，均小于128MiB；这是生产对象计量口径，不是进程RSS或包括全部临时投影/全局LRU的总内存。
- 正常返回后ContextVar为None，捕获的请求状态字典全部清空。复用仅发生在源索引层；_scan的事件、owner及时间投影仍每次生成。没有把request_hit叫作历史读取/写入证据。

### 内容一致性与安全边界

单页和24项的selection JSON、预算后JSON均逐树完全相等；不仅canonical哈希相同，而且无需去除任何cache字段。脚本允许排除的仅为明确cache性能计数/请求预算字段，本样本排除路径数量实际为0。24项仍4ok/20deferred，data_chars=28960；性能改善没有自动补全原先延后的证据。

新增本地合成检查仅修改各自audit目录内fixture，并分别在on/off进程运行：

- on重复访问同一未变源取得1次request_hit，off为0；改源后request_hit为0，旧raw ref被拒。
- 先查晚截点再查早截点，晚结果正文没有进入早期pending事件。
- 正常及异常退出均释放；通过asyncio子task与显式copy_context到新thread检查，不能沿用父执行的请求缓存。自有thread已join，不留后台进程。

这些检查不是操作系统隔离认证；也不证明mtime/size以外的源变化模型。没有更改正式池、报告、runtime或冻结包。

### render_batch_data新wire与旧JSON

在同一份已选定、已预算的data上分别渲染；每种5次未profile计时，编码阶段不做query。新旧返回均经真实investigation.parse_receipt验证并重构为完全相同的data。新wire在本样本均被选择，非强行使用失败codec，也没有隐藏/裁掉事实。

| 负载 | 旧MCP封装字符 | 新MCP封装字符 | 缩减 | 旧render中位ms | 新render中位ms | 新decode中位ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 单changes | 39373 | 35430 | 10.01% | 0.639 | 4.874 | 3.992 |
| 24项changes | 90946 | 80335 | 11.67% | 1.365 | 11.355 | 9.145 |

表中计时来自off进程的五次测量；on对同数据测得旧/新render中位分别0.552/4.897ms及1.264/11.817ms，结论相同。新render包括旧JSON候选构造、pack和receipt，成本不能只报告更短的字符量；相较旧render增加约4–10ms。decode计的是新wire的真实解析/校验/重构，旧decode未另做五次计时，不构造虚假的decode增量。

新格式24项仍超过8万封装字符；可逆、更短并不保证模型理解更好，也不证明exec外层不会截断。没有调查模型重跑，没有把包内数据可重构认证成模型实际收到/读懂全部事实。

### 本候选绑定

- 代码raw_events.py SHA：1d92d13bc7314b0e7ad423a76298a0720f38e5013122b14767fd217dfb20db68。
- change_inventory.py：85d6d9c5e14a17cd7ee7d85e083cfbe47b2ca3abb457cae26dc113a1deb046bd。
- investigation.py：fcac27493a565584f5987a5f2eda920758e243e5b8d78656e43ac7d4898ad634。
- batch_wire.py：a92725a4effe0ed58f2f745e849664ea89cbbc716b06b00e13f1298d1183d7aa。
- 脚本SHA：f248e9c5fb7457b70a74398ff132e0ebf730b726203d5d4181afffadd5bb1525。
- source-reuse-off/result.json：b45a8cc65f3ddbd0d5e6c600f159071a68508a3545502275510fb7c75e67e287。
- source-reuse-on/result.json：db3a7d1afb017d4db9ece053f6fbcedc0454bd3aca17bf80a3d632053b1b4150。

两进程时间为19:03:38–19:05:16Z和19:05:55–19:06:24Z。全部自有进程完成后退出。仅能下结论：在这组固定开发请求上，按源复用减少重复解析且保持已核输出；不能推广成所有池、所有查询或模型端到端收益。
