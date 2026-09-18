# 迁移经验闭环：独立四 skill 包

本目录在 `dev/memory-skills` 开发，独立于 `src/migloop/inquiry`、旧 UI 和服务端。Python 3.10+；JSON 无额外依赖，YAML 输入需要 PyYAML。图校验可选复用已安装的 `migloop[inquiry]`，不包含第二套读写内核。

| Skill | 输入 → 输出 |
|---|---|
| `migloop-repair-triage` | 完整迁移转录 → 问题清单与逐问题 job；只拆分，不归因 |
| `migloop-build-cards` | 一个 job + 完整转录 → 正确输入/首次偏差/最终修复的总结与最小证据链卡片 |
| `migloop-memory-maintain` | 上一版 memory + 新/修订/撤回卡 → 有明确来源的经验及索引新版本 |
| `migloop-memory-recall` | 当前任务与输入 → 目录/全库搜索 → 按需读取适用经验；证据卡默认不加载 |

四个目录一起安装到同一个 skills 根。共享 Python 实现只放在 `migloop-memory-maintain/scripts/memorylib/`，另外三个 scripts 是薄入口；不复制多份内核。前三个skill的操作、模板和命令集中在各自SKILL.md，完整读取即可；第四个按目录/预览→经验正文→来源卡渐进读取经验。旧card.md只作兼容指路，正式模板只有一份。拆分agent不制卡，制卡agent不重新拆整池；派工由宿主负责。

## 安装与验证

```text
python skills/migloop-memory-maintain/scripts/install_bundle.py --destination YOUR_SKILLS_ROOT
python skills/migloop-memory-maintain/scripts/install_bundle.py --destination YOUR_SKILLS_ROOT --update
python skills/migloop-memory-maintain/scripts/install_bundle.py --destination YOUR_SKILLS_ROOT --restore BACKUP_DIRECTORY
python -m pytest skills/tests -q -o pythonpath=src
```

首次安装遇同名目录仍拒绝覆盖；明确加`--update`才替换四个包。更新前先完整暂存新版，再把现有包（包括本地改动）移动到`YOUR_SKILLS_ROOT/../.migloop-skill-backups/<时间-随机ID>/previous/`，stderr打印备份目录，其中manifest.json记录原目录和事务状态。更新会移除活跃包里的旧文件，但它们保留在备份中；其他skill、全局配置、hook与应用代码保持原样。

使用`--restore BACKUP_DIRECTORY`恢复该次操作前的四包状态，包含原先不存在的包；恢复本身也先备份当前安装，支持反向恢复。备份绑定原安装根。更新/恢复期间请结束使用这四个包的任务。安装锁防止并发安装；普通复制/发布错误会回滚，回滚失败保留备份、暂存及恢复记录。进程被强杀或断电时可能留下`installing`事务与锁，需要按manifest核对恢复；四目录替换不是跨进程读者可见的原子切换。

宿主重新发现skills后使用完整路径或`$migloop-repair-triage`、`$migloop-build-cards`等调用。符号链接/junction包不做原地替换。

制卡目标：以观察截止时最终保留状态为正确参照，定位“已收到正确输入，输出却偏离”的位置，再经必要交接连到被修文件。图保留关键正常输入与偏差起点，修复者不是必填节点。多文件可按不同成因选代表文件形成多条示例链，其余目标保留修复记录并明确列为生成归因未决；示例链数与整卡目标覆盖分别报告。每条链使用现有检查器核验；当前检查器仍可能对未解析脚本要求修复锚点，未通过时如实保留缺口。

卡片与经验共用召回语义：`when`写**任务阶段＋具体动作**，`description`写**当前输入可见的适用情境**。阶段来自偏差定位及预防动作，不取修复者角色、固定Stage编号或历史时刻。summary/why解释历史机制，recommendations/how/check说明动作和检查。搜索与浏览预览返回title/when/description；搜索给这三个字段更高匹配权重，没有阶段枚举或硬过滤。

0.4.0新模板填写description；兼容读取、封装和维护旧的case/1与memory/1。旧记录缺字段时不补造语义、不迁移hash或改ID；预览description为空，原when仍可检索。维护者有依据时通过普通提案补齐，发布新版本并沿用依赖复查规则。

`recall.py notice --store STORE` 输出适合首次修改前提醒的宿主无关 payload，**不是已经安装的 Claude/Codex/DevEco hook**。执行调度、云端 OBS/API 和跨租户权限不在本地初版中；不得将此本地文件接口直接公开为无鉴权服务。

## 数据与身份

- provenance 自动采集 CC/Codex JSONL 的 session、agent、模型、客户端版本及原文位置；DevEco SQLite 用 `--session-id` 限定根及后代，只读 session/message 的相关信息。
- migration 与 analysis 元数据分开；多模型不压成单一模型；缺失版本标 unknown。`<synthetic>` 等转录占位不当成真实模型。
- 每份转录保留模型切换顺序及原文位置，采集器与封装器各记录实际包版本/hash；不能将同 session 的所有模型都认作某一问题的作者模型。
- 服务端补充文件只接受 migration/analysis 两个已知字段集合，不把工具输出或任意配置整包复制入卡。原始字段仍未由本地脚本鉴真。
- 知道的信息必须由 server/harness 提供，不能让调查模型猜模型、工具、skill 版本。当前 collector 的版本不冒充历史迁移工具版本。
- job/card 身份与可变化的证据 hash 分开；服务端迁移 ID 优先，否则使用本地材料位置作为明确的局部身份。补充原文或重排问题不更改同名问题身份。更名/搬迁/合拆应保留既有身份或显式撤回旧卡，不悄悄重新命名成无关卡。
- 卡片可包含多目标 graph；每目标导出原格式 compact JSON view，供旧 inquiry 提交器加载。整张新卡及 memory 不宣称已经接入旧网页上传。
- 只做结构封装的卡明确标未运行图校验。可选 `--db` 产生现有 checker 的实际反馈，不能把机械通过说成原因/建议已证明正确。

## Memory 的边界

本地库保存不可变快照与卡片版本，通过原子 HEAD 更新发布。写入锁与 base_revision 防止覆盖新版本；失败不发布半套索引。目录由 lesson 记录即时生成，无独立手写链接账本。

经验绑定 `case + claim + revision`；卡变更/结论撤回会使直接与传递依赖进入 needs_review，默认不召回。其他证据可能足够时也须显式重新审核，不根据多数票自动恢复。旧卡保留用于审计。

首版检索是目录导航 + 全库词项/CJK 双字匹配，可分页/批量读；不是 embedding 检索，也不承诺召回率。默认只有 active 经验，维护可显式查所有状态。模型、平台筛选保留数据基础，当前不实现过滤 UI/API；整个迁移用过某模型不等于每条原因都由该模型造成。

本目录测试是合成契约与安全边界测试，不是新的真实迁移正确率。真实评估应分别测归因、召回/误用和生成收益，不能把脚本通过当成三者的替代。
