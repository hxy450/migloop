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
