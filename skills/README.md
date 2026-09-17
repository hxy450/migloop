# 迁移经验闭环：独立四 skill 包

本目录在 `dev/memory-skills` 开发，独立于 `src/migloop/inquiry`、旧 UI 和服务端。Python 3.10+；JSON 无额外依赖，YAML 输入需要 PyYAML。图校验可选复用已安装的 `migloop[inquiry]`，不包含第二套读写内核。

| Skill | 输入 → 输出 |
|---|---|
| `migloop-repair-triage` | 完整迁移转录 → 问题清单与逐问题 job；只拆分，不归因 |
| `migloop-build-cards` | 一个 job + 完整转录 → 正确输入/首次偏差/最终修复的总结与最小证据链卡片 |
| `migloop-memory-maintain` | 上一版 memory + 新/修订/撤回卡 → 有明确来源的经验及索引新版本 |
| `migloop-memory-recall` | 当前任务与输入 → 目录/全库搜索 → 按需读取适用经验；证据卡默认不加载 |

四个目录一起安装到同一个 skills 根。共享 Python 实现只放在 `migloop-memory-maintain/scripts/memorylib/`，另外三个 scripts 是薄入口；不复制多份内核。入口说明保持短，详细模式见各自 references。拆分 agent 不制卡，制卡 agent 不重新拆整池；派工由宿主负责。

## 安装与验证

```text
python skills/migloop-memory-maintain/scripts/install_bundle.py --destination YOUR_SKILLS_ROOT
python -m pytest skills/tests -q -o pythonpath=src
```

安装只创建不存在的四个技能目录；已有目标拒绝覆盖，不修改全局配置、hook 或应用代码。已安装的同名旧版本应有意识地更新/备份，不自动删除。宿主重新发现 skills 后使用完整路径或 `$migloop-repair-triage`、`$migloop-build-cards` 等调用。

制卡的目标约定：观察截止时最终保留状态相对生成结束状态是正确目标；不要求重新证明修复有效。历史上被后续修复推翻的内容不能当最终经验。图允许多个偏差起点，各自经必要交接连到被修文件；最好带上证明各起点输入正确的关键输入节点，但不枚举全部输入、写者或调查调用。when 描述未来任务事前可识别的情境，recommendations 描述可执行的预防动作；历史时间与节点只作为证据。

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
