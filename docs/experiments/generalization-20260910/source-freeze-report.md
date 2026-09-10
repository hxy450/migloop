# 新队列源冻结与注册元数据验证

本轮只冻结原始字节并核注册路径/数量，不阅读具体归因、不建gold、不运行调查模型、不执行历史命令。两队列的13个既定目标、原顺序、曝光标签及三锚点均保持不变。源冻结通过不等于工具信息可达性通过。

## 实现与测试

- [prepare_transfer_sources.py](prepare_transfer_sources.py)：prepare、verify、registry三个公共入口。只创建新输出；已存在目录拒绝；失败保留半成品且没有SOURCE_READY，不覆盖、不删除。
- [安全测试](../../../tests/test_prepare_transfer_sources.py)：初次真实冻结前37 passed、1 skipped；全文件注册/编码gap合同追加后39 passed、1 skipped。跳过的是本机权限不允许创建的合成文件系统symlink；ZIP symlink及FIFO/socket/device等特殊项拒绝测试均通过。重复成员测试产生一条预期ZipFile告警。
- ZIP在创建输出前完成成员路径、绝对/drive-relative、父目录、大小写及前缀类型撞名、NUL、Windows保留名/ADS、符号链接/特殊项、大小上限等预检。所有落点检查解析后仍在新目录中，并逐文件exclusive写入，不调用extractall或历史脚本。
- 实际arch11 ZIP有384个反斜杠成员名。首轮严格预检在创建输出目录前拒绝；随后增加显式分隔符规范化及测试：将反斜杠转为层级分隔符，再检查越界、别名和撞名。不扁平化，保留original_name到archive_members供复核。
- 防护面是已验证路径、普通文件和非敌对并发场景，不声称它提供OS沙箱或抵御任意并发文件系统替换攻击。

## 已冻结来源

输出根：

C:/Users/hongy/projects/_migloop-eval-20260909/generalization-20260910/source-freeze-1

source-manifest.json SHA-256：

92d42b2d7b7dcf6a5cbebb4498f2036ca0130be56a65f218e57d55905c9d0e89

| 队列 | 文件 | JSONL | 根 | 侧文件/层级 |
| --- | ---: | ---: | --- | --- |
| dynamic1 | 169 | 78 | 5629edf4-bf1b-4616-81fb-e2c7b3c2ca26.jsonl | 77子JSONL位于workflows深层；91非JSONL全部保留 |
| arch11 | 385 | 193 | 462439ee-b5af-4443-8a58-2e785a2ef826.jsonl | ZIP385成员全为文件；192子JSONL与192meta全部保留 |

dynamic1原导出：

C:/Users/hongy/projects/migloop/dist/_sources/dynamic1-20260908/C--Users-hongy-projects-transfer-app-dynamic1

原目录完整文件/目录规范清单冻结前后digest均为d522acaaa59203dbbaf7f0dcaa2883caf1bd372523a1879c39258ed5cd01d67d。逐文件内容与资格清单全部匹配；资格清单原规范JSON digest 0810f41cf0aafaf745835639ac4eb60c902c22da660d3382e59e32c4175c8f6b亦校验。目录清单、原资格列表和新排序files列表的digest算法/顺序不同，不把不同digest误作内容变化。

arch11原ZIP：

C:/Users/hongy/projects/migloop/dist/arch11-session-462439ee-full.zip

压缩归档字节冻结前后SHA-256均为9e3670140402600547399b1ed387da5d60bc52a413169abd733e9ea1491adf69；解压实际171013132字节。每成员CRC经ZipFile流读取验证，再记解压内容SHA；输出逐文件重新哈希匹配。原池、原ZIP及冻结池无删改。

## Harness接口

source-manifest.json的schema为migloop-transfer-source-freeze/1，status为sources_frozen。cohorts中提供：

- id、相对pool、绝对sid/roots、root_transcript；
- files逐项path/bytes/sha256、directories、file_count/jsonl_count/file_manifest_sha256；
- origin前后hash、archive_members原名/规范名/成员元数据；
- generation_end、repair_qualification_start、observation_end，三个字段不合并；
- tasks的id/relative_target/original_target/exposure，以及队列曝光边界。没有携带资格事件、actor结论或预期原因。

任务ID为DYNAMIC1-01…06、ARCH11-01…07。SOURCE_READY.json只绑定源manifest字节，明确不认证registry通过。运行器还必须核相同source manifest及本次candidate code_digest绑定的全队列注册验证成功。

| 队列 | generation_end | repair_qualification_start | observation_end |
| --- | --- | --- | --- |
| dynamic1 | 2026-07-29T01:59:05.818Z | 2026-07-29T02:01:30.213Z | 2026-08-03T03:24:28.258Z |
| arch11 | 2026-07-18T01:23:20.239Z | 2026-07-18T01:23:52.130Z | 2026-07-20T15:34:16.751Z |

## 冻结v4真实注册失败记录

使用指定的file-first-10/tools-v4/code，不用live替代。通过真实service.observation_scope、service.session_ledger和transcript_store.sources检查，只输出路径/数量元数据。reader内部正常解析转录，但本审阅不展开其任务/修改内容。

registry-validation-v4.json SHA-256：

0c092ab5ef60599455a6c784b6af2aec485970e60529b1b24b45abc93666b473

绑定的code_digest为28b0ab3f71102060a64b9532d7808294096caecbcbf09c5d923e61bd38e5fcbb，与父端声明冻结v4一致；运行前后完整package inventory相同。

| 队列 | 实际registry | 期待JSONL | missing | unexpected | passed |
| --- | ---: | ---: | ---: | ---: | --- |
| dynamic1 | 1 | 78 | 77 | 0 | false |
| arch11 | 193 | 193 | 0 | 0 | true |

dynamic1只注册根。该v4的collect_cc/collect_cc_pool及pool_key使用直接subagents/*.jsonl发现，而77个子源全部位于更深workflow路径；缺失包含agent转录及journal，完整名单已在失败artifact保存。源未搬动、未扁平化，也没有把磁盘文件数冒充注册数。总passed=false，不能放行。

注册验证schema为migloop-transfer-registry-validation/1，提供source_manifest_sha256、code_digest、runtime_before/after、runtime_stable、cohorts各自sid/roots/registered/missing/unexpected/passed及总passed。失败原件保持不动；修复提交后的新candidate须另写新的registry验证文件。

## dynamic1侧文件：不能把78/78误称169文件信息等价

独立artifact：dynamic1-sidecar-metadata.json，SHA-256为0923e808b7373c0167a3b1ad4dfc4598663c50faac61db1b9f5575050caa911c。

仅从冻结字节提取路径、扩展名、JSON键/类型、字符串长度和hash，不显示或解释任何文本值。91个非JSONL如下：

| 类型 | 数量 | 结构/长度元数据 |
| --- | ---: | --- |
| agent meta JSON | 70 | 顶层键为agentType、spawnDepth |
| workflow JSON | 7 | 顶层含runId、timestamp、taskId、script、scriptPath、result、agentCount、logs、durationMs、summary、workflowName、status、startTime、phases、defaultModel、workflowProgress、totalTokens、totalToolCalls |
| tool-results/*.txt | 10 | 均为UTF-8非JSON；20543–191988字符 |
| workflow scripts/*.js | 4 | 均为UTF-8非JSON；9548–25521字符，作为字节保存，未执行 |

七份workflow JSON的script字段为7954–25521字符；result为1–2键对象；logs为2–4项列表；summary为62–97字符；workflowProgress为7–20项列表。其嵌套字段共有66个promptPreview、62个resultPreview，均401字符。这证明JSONL之外至少保存了命名为prompt/result预览、脚本和workflow配置结构的内容入口；不证明预览完整、何人消费、与JSONL完全重复或它们的因果作用。

10份txt位于tool-results目录，名称包括工具call_id式名称；仅凭路径和长度登记为外存工具输出候选，未据此认定具体输出语义或成功。工具若只索引JSONL，这14份文本文件及7份workflow JSON的内容可达性必须单列；原始组可读取完整池文件，不能因未来JSONL registry修成78/78就宣布两组信息等价。

目前没有做内容去重/语义等价判断，也没有将侧文件字符串借用JSONL时间、actor或调用身份。后续若引入侧文件读取，需保持独立定位和明确时间未知边界。

## 新candidate的全文件注册口径

父端根据侧文件发现要求新的验证以全文件整集为准：dynamic1期待169项、arch11期待385项；JSONL分别78/193另列。验证函数已更新，source-manifest及旧registry-validation-v4.json均未改。旧失败文件继续表示当时JSONL口径，不伪装成全文件检查。

新artifact必须声明coverage_kind=all_registered_text_or_decode_gap（顶层及各cohort），registered继续为相对POSIX路径；registered_count/expected_count为全文件，registered_jsonl_count/expected_jsonl_count单列。passed表示注册整集一致及整体code稳定，不能单凭passed推断全部正文可读。

readability检查只对已注册文件做UTF-8增量解码计数，不输出文字、不分析语义。registered_text_decodable_count、decode_gaps及all_expected_text_decodable独立登记；二进制或解码失败不计作正文可读。它仍不是具体record/search API已完整交付每个文件的认证。新增合成测试验证：即使JSONL数量齐全，漏一个meta附件仍失败；解码错误明确为gap。

运行器应要求新的全文件coverage_kind及与拟用candidate一致的code_digest，不可复用旧v4的JSONL结果。当前仍等待提交后的新candidate，不对live预先宣告通过。

## 当前停止点

源字节冻结、脚本及合成测试已完成；冻结v4注册失败与侧文件覆盖风险均已如实留档。等待父端提交新candidate后再做新的注册验证，gold及模型队列仍未启动。所有自有子进程已结束，无运行时/旧runner/旧成绩改动。

## candidate-source-v1真实门（2026-09-10后续，未通过）

新候选为generalization-20260910/candidate-source-v1，manifest SHA为60640cdb5075538a783cc5c93e9ab881f5d4a4b21b6d83672ef7e7200311e1bd，实际code digest为0cf294977c1c622fe0503123f369e4956a328aec83954303bad3c4bdb4e06455。源及代码均通过运行前后哈希复核，原source-manifest及registry-validation-v4.json未改。

新registry-validation-source-v1.json（SHA af82a7fd0957857ed0c6c20ad719f7de15ed737bdda0caf71df31007507c89f3）通过：dynamic1为169/169、JSONL78；arch11为385/385、JSONL193；缺源/额外源/UTF-8 decode gaps均为0。这只完成全文件注册与编码门。

真实stdio MCP smoke使用独立smoke_transfer_sources.py，无模型、无gold。每队列默认file（不提供view）limit=1，以及q=""的pool search、include_undated=true；同批max_chars=100000，不因失败提高预算。辅助文件按相对路径排序选第一份；search的offset仅由原始物理行的未知时间顺序计数得到，不使用因果关键词。record使用返回scope和include_undated=true，完整拼接字符续页，与每个原始物理行payload直接比较。所有回执绑定真实响应正文、请求、ledger及scope；正文不写入元数据报告。

| 队列 | file overview | 空pool search | 首aux record完整payload | 门 |
| --- | --- | --- | --- | --- |
| dynamic1 | deferred，未交付data/原文 | ok，首aux ref在回执中 | ok，48字符/1物理行 | fail |
| arch11 | ok，scope/body scope及385源计数一致 | ok | ok，135字符/1物理行 | pass |

两份aux样本均ts=null、time_status=undated、owners=[]；访问不认证actor或历史时刻。所有aux注册元数据同样无owner且timestamp_policy=unknown：dynamic1为98项（包括7份作为辅助材料注册的JSONL journal，不等同于91个非JSONL），arch11为192项。完整往返仅认证所选一份文件的全部物理行payload；record接口不交付CR/LF分隔符及首行BOM，不能写成通用byte-file下载，也未认证其余每个附件的全文交付。

失败原因已用同候选同参数本地selection元数据确认，未冒充MCP正文交付：dynamic1概览selected大小3,650,409字符；body_sources为1,822,413字符，coverage为1,820,403字符，两字段约占99.79%，sections仅5,398字符。body_sources.gaps和coverage.native_source_gaps重复包含4,228条（TXT3,605、JS623），全部带malformed标记；raw_index.gaps=0。冻结raw_events.py:289虽对unknown时间源跳过_native，291–292仍对每个record.malformed追加完整address/source_path/error。因此是纯文本附件被逐行当坏JSON记录放大，并非这些文件解码失败。实际batch的file状态deferred、delivery.records=[]；同批search为ok。不能把本地能构造selected数据当交付成功。

全部尝试保留在source-freeze-1下，不覆盖失败：

| 产物 | SHA-256 | 范围 |
| --- | --- | --- |
| smoke-source-v1.json | 314462af7f8f28e60453319929c3bde189eb0a2c7ae2543992153aef52b60fe0 | 首次审计脚本未对aux路径做Windows normcase，预检误拒绝；未到MCP |
| smoke-source-v1-attempt2.json | 21d3960f21aee13d8aa73a0652034c4a56a412d7981a70cd4423e173060726fb | 修审计脚本后真实MCP；arch11全门通过，dynamic1状态断言失败被ExceptionGroup包裹 |
| smoke-source-v1-attempt3-dynamic1.json | 894d6a250c02803300c19026be1415a3adb05a03ffbc34da8ce95dd2c09746f4 | 仅dynamic1，保留实际deferred/ok状态、回执、尺寸与内层断言位置 |
| smoke-source-v1-attempt4-dynamic1.json | d6a79a3895247c542f93c1755949fb0f1c427541671d61fa1324f6056c31cd4a | 仅dynamic1；保持overview失败，同时完成独立aux往返与本地元数据分解 |

最终源内容门未通过，父端暂停gold，待显式冻结后续修复候选再验证；未改candidate、预算、生产代码或旧runner。所有自有MCP和审计进程已退出。

## 文本附件修复与后续候选准备

真实失败定位后，非 JSONL 附件统一作为可定位的原始物理文本行读取，而不是逐行尝试解释为 JSONL 事件。正文、内容哈希、旧/新原文引用和分页保留；JSON 外观的文本也不获得事件时间、actor 或 JSON Pointer。真正损坏的 JSONL 和 UTF-8 解码失败继续显式报告 gap。独立回归还发现并修复了去掉虚假 JSON Pointer 后文件相关文本被 unknown payload 过滤的问题：相关提及可查，但不因此成为读写事实。

最新完整测试结果为 2,653 passed、9 skipped、1 warning，229.98 秒；warning 来自 ZIP 重复成员反例。原默认 pytest 临时目录权限错误未被掩盖或修权限，本次使用单独新建且范围受控的 basetemp。测试通过不替代真实 MCP 门，下一候选必须使用相同 100,000 字符预算重新验证；candidate-source-v1 及所有失败产物保持不变。尚未建立新 13 文件因果参考答案，也未启动其模型调查。

## candidate-source-v2 真实门通过，随后开放参考取证

修复提交为 `6953972`，另保留已有用户工作区改动；准确运行身份以完整冻结包而非单个 commit 为准。candidate-source-v2 manifest SHA 为 `19d9a70955694ce4c9fce5aaedf77dcfa80ffe6f7e66a21eac74cc9b8367434b`，code digest 为 `50c63af5702f8671811833bf3bf38720d766cecc41f18859a88e25b27434786d`。

`registry-validation-source-v2.json`（SHA `29ec08759b6cd53e6fae015916282e7180dbfa73381bd2b94727aedf46211830`）全门通过：dynamic1 169/169、JSONL78；arch11 385/385、JSONL193；缺、额外、UTF-8 decode gaps 均为0。

`smoke-source-v2.json`（SHA `e99f7636252853a4f11801f254c821ddb53fa0d2844615830ba6d31ddd9b17f3`）使用同样 100,000 字符预算、同样默认 overview 和首附件选择规则：两队列 file/search/record 全部 `ok`、`budget_adjusted=false`；overview 原始 data 分别为10,239和10,156字符。dynamic1 不再是 v1 的3,650,409字符 deferred。两份样本附件的原始引用及内容哈希保持一致，分别48/135字符、各1物理行完整往返；时间仍未知，owners仍为空。未认证所有附件逐份完整交付或任何因果主张。

源与代码前后哈希稳定；原始 source manifest、旧失败产物及 run_transfer 字节未变，自有进程均已退出。门通过后才授权新13文件的参考建立；先取原始修改及间隔/候选命令，再独立复核和冻结 core，尚未运行新调查模型。候选代码不能依据这些新答案调整。
