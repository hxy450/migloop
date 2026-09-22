# 迁移经验闭环：独立四 skill 包

本目录维护四个 skill 的源模板与共享业务代码；发布包各自自包含，只需 Python 3.10+。制卡包携带从 `src/migloop/inquiry` 构建的同一新内核，其他包不携带内核。YAML 的纯 Python 依赖随包提供；运行时无需 pip、MCP、migloop 源码仓或 PYTHONPATH。不包含第二套读写实现，也不打包旧 UI/服务端。

| Skill | 输入 → 输出 |
|---|---|
| `migloop-repair-triage` | 完整迁移转录 → 问题清单与逐问题 job；只拆分，不归因 |
| `migloop-build-cards` | 一个 job + 完整转录 → 正确输入/首次偏差/最终修复的总结与最小证据链卡片 |
| `migloop-memory-maintain` | 空库或上一版 memory + 新/修订/撤回卡 → 有明确来源的经验新版本 + 分层 Markdown 阅读包 |
| `migloop-memory-recall` | 当前任务与输入 + index.md → 用普通文件读取按需展开相关目录和经验；证据卡默认不加载 |

源码只维护 `migloop-memory-maintain/scripts/memorylib/` 与现有 inquiry，新发布目录是自动构建产物，不在其中单独改代码。每个 skill 有自己的 `scripts/_runtime/`，可单独搬走；发布包多份相同运行文件不代表多套实现。前三个skill的操作、模板和命令集中在各自SKILL.md，完整读取即可；第四个按目录/预览→经验正文→来源卡渐进读取经验，正常使用只需召回指引与阅读包，不依赖 Python/MCP。旧card.md只作兼容指路，正式模板只有一份。拆分agent不制卡，制卡agent不重新拆整池；派工由宿主负责。

## 安装与验证

发布构建在开发环境进行（Python 3.10+、PyYAML==6.0.3）：

```text
python skills/migloop-memory-maintain/scripts/build_bundle.py --out NEW_RELEASE_OUTSIDE_REPO
```

将生成的任意 skill 文件夹单独复制到目标 skills 目录即可使用。制卡包含完整查询/校验所需的新内核 Python 模块，CLI 直接调用，不另起 MCP 服务；网页和服务端仍使用原来的内核源码。每包 `package-manifest.json` 记录版本、源码提交/脏状态、逐文件摘要与第三方依赖；运行入口验证文件，避免包内被另行修补而不知情。PyYAML 纯 Python 实现及许可证随包交付，不包含平台二进制扩展。

批量安装仍使用已有可恢复安装器；从源码调用时先构建完整发布包，再安装：

```text
python skills/migloop-memory-maintain/scripts/install_bundle.py --destination YOUR_SKILLS_ROOT
python skills/migloop-memory-maintain/scripts/install_bundle.py --destination YOUR_SKILLS_ROOT --update
python skills/migloop-memory-maintain/scripts/install_bundle.py --destination YOUR_SKILLS_ROOT --restore BACKUP_DIRECTORY
python -m pytest skills/tests -q -o pythonpath=src
```

新增独立发布测试以 `python -I -S` 运行，禁用 site-packages/PYTHONPATH，把各 skill 分开放置，验证 YAML 输入、元数据/派工、自动建库、索引复用、正常/错误关系、经验维护/导出及 hook 安装。源码模板不是面向最终用户的安装包。

首次安装遇同名目录仍拒绝覆盖；明确加`--update`才替换四个包。更新前先完整暂存新版，再把现有包（包括本地改动）移动到`YOUR_SKILLS_ROOT/../.migloop-skill-backups/<时间-随机ID>/previous/`，stderr打印备份目录，其中manifest.json记录原目录和事务状态。更新会移除活跃包里的旧文件，但它们保留在备份中；其他skill、全局配置、hook与应用代码保持原样。

使用`--restore BACKUP_DIRECTORY`恢复该次操作前的四包状态，包含原先不存在的包；恢复本身也先备份当前安装，支持反向恢复。备份绑定原安装根。更新/恢复期间请结束使用这四个包的任务。安装锁防止并发安装；普通复制/发布错误会回滚，回滚失败保留备份、暂存及恢复记录。进程被强杀或断电时可能留下`installing`事务与锁，需要按manifest核对恢复；四目录替换不是跨进程读者可见的原子切换。

宿主重新发现skills后使用完整路径或`$migloop-repair-triage`、`$migloop-build-cards`等调用。符号链接/junction包不做原地替换。

制卡目标：以观察截止时最终保留状态为正确参照，定位“已收到正确输入，输出却偏离”的位置，再经必要交接连到被修文件。图保留关键正常输入与偏差起点，修复者不是必填节点。多文件可按不同成因选代表文件形成多条示例链，其余目标保留修复记录并明确列为生成归因未决；示例链数与整卡目标覆盖分别报告。0.7.1 起检查器直接核到目标的历史交接，不再要求修复窗口写入锚点。缺边/倒序仍拒绝；path_feedback 保留具体节点和冲突证据，可选相关操作不作为缺边提示。

制卡的 unknown 可省略；graph 的 summary/recommendations 默认复用卡级文字，只有分支不同才填写。封装保持原始 draft，单目标 view 补入这些已由模型填写的卡级文字，不生成新结论。字段错误按 graph/node/edge 位置返回，等价时区表达不算更改任务窗口。

卡片与经验共用召回语义：`when`写**任务阶段＋具体动作**，`description`写**当前输入可见的适用情境**。阶段来自偏差定位及预防动作，不取修复者角色、固定Stage编号或历史时刻。summary/why解释历史机制，recommendations/how说明动作。0.7.2 起 lesson 的 `check` 可省略或为空，阅读包仅在有内容时显示“可选检查”；只在条件疑问、输入冲突或关键假设需要核实时按需执行，优先复用正常测试，不改变来源/版本的机械校验。阅读目录提供时机、情境和例外预览；只有相关经验才展开正文。

0.4.0新模板填写description；兼容读取、封装和维护旧的case/1与memory/1。旧记录缺字段时不补造语义、不迁移hash或改ID；预览description为空，原when仍可检索。维护者有依据时通过普通提案补齐，发布新版本并沿用依赖复查规则。

0.5.0增加文件阅读发布：维护者运行`memory.py export --store STORE --out NEW_DIRECTORY`，宿主向迁移agent提供召回skill和生成的`index.md`。Claude Code 可另行安装项目级首次修改提醒，见`migloop-memory-recall/references/claude-hook.md`；只有安装并验证项目配置后才算接通。Codex/DevEco hook、云端 OBS/API 和跨租户权限尚未接入。旧`recall.py notice`仍是兼容诊断payload，不是已经安装的hook，也不是新版阅读入口。

## 文件夹式阅读

```text
python skills/migloop-memory-maintain/scripts/memory.py export --store STORE --out NEW_APPLICATION_DIRECTORY
python skills/migloop-memory-maintain/scripts/memory.py export --store STORE --out NEW_DEVELOPMENT_DIRECTORY --link-cards
```

导出根`index.md`只列一级主题；每个子目录有自己的`index.md`，列直接子主题与本级经验预览；一条经验一个`*.lesson.md`。可以同时读多个分支，按当前任务选择，未遍历全库不等于召回未完成。目录不复制后代全文，经验正文不截断。

只导出active记录，保留ID、版本、when/description/unless/why/how/check及来源绑定。默认阅读包不包含来源卡或本机路径，可单独分发；开发版`--link-cards`指向store中确切版本的卡片文件，链接只适用于保持相对位置的本地目录。manifest.json记录版本和文件校验和供维护审计，不是模型入口。两者是同一份store的派生视图，不维护第二份经验真理源。

导出前检查所有可见主题的介绍及来源版本，完整暂存后再发布到**全新**目录。既有目录拒绝覆盖，修订后导出新版本并交付新入口；旧包不会随来源撤回而自行失效。经验和目录调整通过维护提案回到store，再重新export。CATALOG.md全量汇总仍可供人审阅，但不作为召回入口。

## 数据与身份

- provenance 自动采集 CC/Codex JSONL 的 session、agent、模型、客户端版本及原文位置；DevEco SQLite 用 `--session-id` 限定根及后代，只读 session/message 的相关信息。
- migration 与 analysis 元数据分开；多模型不压成单一模型；缺失版本标 unknown。`<synthetic>` 等转录占位不当成真实模型。
- 每份转录保留模型切换顺序及原文位置，采集器与封装器各记录实际包版本/hash；不能将同 session 的所有模型都认作某一问题的作者模型。
- 服务端补充文件只接受 migration/analysis 两个已知字段集合，不把工具输出或任意配置整包复制入卡。原始字段仍未由本地脚本鉴真。
- 知道的信息必须由 server/harness 提供，不能让调查模型猜模型、工具、skill 版本。当前 collector 的版本不冒充历史迁移工具版本。
- job/card 身份与可变化的证据 hash 分开；服务端迁移 ID 优先，否则使用本地材料位置作为明确的局部身份。补充原文或重排问题不更改同名问题身份。更名/搬迁/合拆应保留既有身份或显式撤回旧卡，不悄悄重新命名成无关卡。
- 卡片可包含多目标 graph；每目标导出原格式 compact JSON view，供旧 inquiry 提交器加载。整张新卡及 memory 不宣称已经接入旧网页上传。
- 普通 pack 自动准备或复用同一迁移的索引并运行现有 checker；显式 `--db` 可使用材料匹配的既有索引。仅 `--draft-only` 可跳过关系校验，清楚标为未核草稿。不能把机械通过说成原因/建议已证明正确。

## 索引与数据放置

`cases.py prepare --job JOB` 可在派工前准备一次，pack/query/page 复用同一份索引和任务级反馈。默认索引放在 dispatch 的 provenance.json 旁 `.inquiry/`，按源材料指纹、位置和内核指纹隔离；并行调查员不各自复制一份数据库。单个建库锁避免并发重建，半成品不会发布。输入转录保持只读，SQLite/情景卡/store/阅读包都在工作目录，不进入 skill 程序包。

原生 CC/Codex JSONL 直接建索引。现有 DevEco 元数据支持保留，但 inquiry 尚未直接解析其 SQLite 原库；原库制卡明确报不支持，不将元数据采集误称为读写校验。平台适配应进入唯一新内核，不能在 skill 层另写一套判边器。

## Memory 的边界

本地库保存不可变快照与卡片版本，通过原子 HEAD 更新发布。写入锁与 base_revision 防止覆盖新版本；失败不发布半套索引。阅读目录从固定快照导出，无独立手写链接账本。

经验绑定 `case + claim + revision`；卡变更/结论撤回会使直接与传递依赖进入 needs_review，默认不召回。其他证据可能足够时也须显式重新审核，不根据多数票自动恢复。旧卡保留用于审计。

使用侧为模型自主导航 Markdown 文件，普通文件搜索可作补查，不承诺召回率。原词项/CJK双字匹配脚本留给旧调用方和维护诊断；维护可显式查所有状态。模型、平台筛选保留数据基础，当前不实现过滤 UI/API；整个迁移用过某模型不等于每条原因都由该模型造成。

本目录测试是合成契约与安全边界测试，不是新的真实迁移正确率。真实评估应分别测归因、召回/误用和生成收益，不能把脚本通过当成三者的替代。
