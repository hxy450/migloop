# 核心裁决口径对账

按既有 [protocol v1](protocol.md)、冻结 reference-v1 和三份 common-task 复核。**core 不是 facts 满项率**：通过需核心事实/近因和重要反证正确；可恢复的必要环节未核为 partial；核心责任/变更/时序错或虚称行为已验证为 fail。不新加题目门槛，也不因 V8 省 token 放宽。

## 哪些遗漏影响核心

- **S3 的 H5 名称是 minor**：若三个本轮站点及 AppLoad 透明＋Pay/Renew 深色全对，未把既有 H5 算成本轮、验证边界正确，漏点名 H5 不妨碍 core=pass。H5 的事实行仍 partial。首轮 [正式裁决](formal-adjudication-legacy.md) 已采用此口径，不是现在新增豁免。
- **D2 的 may-throw WARN 是 minor**：若构建成功、observer 修改及未触发运行验证的边界正确，可 core=pass；不是允许声称零 WARN 或把 WARN 当失败。
- **S4 的 Slice8 实际输入链是 mandatory**：题目问原实现与多次修改原因；正确 Kotlin 在整写前已返回是池内可恢复近因，没核不能用“未知”通过。
- **S1 的删除者和核心 BACK 修复是 mandatory**：entry-setup 不能错归 Slice11；onWillDismiss 不能被后面的复位兜底替代。
- **S2 的早已有据与真实隐藏修复是 mandatory**，但不指定必须某一 locator。V8 已开早期 ui-manifest，可支持“不是后置新增”；未读 root L404 本身是细项不足。只确认恢复、漏掉实际入页隐藏，仍是核心缺项。
- Dice 新发现的主机 10/10 回执保持独立 addendum；原始组和工具组同尺度，不偷偷改变旧 D1 核心分母，且它不认证 AppStorage 桥键。

## 当前已裁决运行

`raw` 的 Dice/Splash 来自 formal-v7；Member 来自 formal-v6-document，均是同冻结题目/池。V8 三文件两rep现已补齐。每个 run/q 的原始依据、报告路径、细项状态/计数在 [JSON](core-rubric-reconciliation.json)。

| 运行 | 题目核心 | 一句依据／保留的缺项 |
|---|---|---|
| Dice raw rep1 | D1 **partial**；D2 **pass** | 桥后置阶段正确但生成实际输入未核；observer/SDK/构建边界正确。 |
| Dice raw rep2 | D1 **partial**；D2 **pass** | 同样漏生成输入；后来 10/10 按来源主张补充，不冒称桥键认证。 |
| Splash raw rep1 | S1 **fail**；S2 **partial** | 把核心删除作者错归 Slice11；系统栏只引后期主题，未证明生成前已有输入。 |
| Splash raw rep2 | S1 **partial**；S2 **partial** | 删除环节未查、onWillDismiss 引文不支持；系统栏只查恢复，隐藏未核。 |
| Member raw rep1 | S3 **pass**；S4 **partial** | 站点/值/H5正确；漏 Slice8 输入及第一轮 ForEach。价格 L605 错引另列审计问题。 |
| Member raw rep2 | S3 **pass**；S4 **partial** | 正确排除既有透明，未点名 H5 属 minor；两轮修复正确但原实现近因未核。 |
| V8 Dice rep1 | D1 **pass**；D2 **pass** | 实际补足 generator 输入，后置桥/observer/构建边界正确；WARN 与 10/10 通道漏项留在完整性层。 |
| V8 Dice rep2 | D1 **pass**；D2 **pass** | 主链成立、补了10/10历史总结；另有memory在修复后这一**实质时序错误**，完整标注必须修正。 |
| V8 Splash rep1 | S1 **partial**；S2 **partial** | 找对删除者和早期需求，但两个已执行脚本 L346/onWillDismiss、L485/隐藏未展开。 |
| V8 Splash rep2 | S1 **pass**；S2 **pass** | 两脚本完整输入/写后回执与主链已核；正确决策挂错v38、生命周期候选误认主题复核，均使完整标注不通过。 |
| V8 Member rep1 | S3 **pass**；S4 **partial** | H5漏名不降正确站点/值核心；Slice8输入没核，红节点及尾后v40错挂另列。 |
| V8 Member rep2 | S3 **pass**；S4 **partial** | 同样正确站点/值、漏H5；仍没查Slice8，非红v40与S3宽repair锚点仍须审计。 |

报告指针：[raw Dice/Splash](v7-baseline-legacy.md)、[raw Member](v6b-adjudication-member-raw.md)、[V8 Dice](v8-adjudication-dice.md)、[V8 Splash](v8-adjudication-splash.md)、[V8 Member rep1](v8-adjudication-member.md)、[rep2](v8-repeat-adjudication-member.md)。

## 明示修正，不暗改旧文

1. 旧 raw Splash rep1 文档一面认定“核心删除作者错归”，一面写 core partial。按 protocol 原有“核心责任错误→失败”，本对账改为 **S1 fail**；旧细项 contradicted 和原始证据不变。
2. V8 Member 两稿的“核心不完整”措辞过宽。S3 应为 **core pass、H5 minor、完整标注仍可能不通过**；S4 才因 mandatory 输入链缺失为 partial。原来每稿 4 supported＋2 partial 的事实细项不变。
3. raw Splash rep2 的错误引文不能因为结论碰巧真实而获得证据通过；但它没有相反的修复事实断言，core 因关键链未完成为 partial，完整引用审计不通过。不能用一条可定位 ID 认证引文内容。

4. [V8 Dice rep2](v8-repeat-adjudication-dice.md) 的 D2 直接worklist来源正确，仍core pass；但它把21:12已有的memory反馈说成21:19修复后，错误排除早期材料。不是minor遗漏，也不是新加oracle必填项；JSON以 `extra_false_claims` 和 `annotation_requires_correction=true` 明确记录，完整标注不通过。所有既知错作者/错引/错绑也同字段单列，不能只数core通过来宣称正确性提高。

5. [V8 Splash rep2](v8-repeat-adjudication-splash.md) 真正补查两脚本的完整输入/成功回执，整段notes也交代dismiss/隐藏修复；不要求必须说“实际执行”四字。S1 reason讲正确Slice11阶段，并非直接断言v38的DBPPT import动作加入isModal，因此core pass，错误精确进入坐标另列material；S2的Android候选错适配也明确false，不是minor。

原始组无需 YAML/basis/coverage，不据此扣分；工具组 core pass 也不抵消伪 repair、错挂事件或伪造历史边。两组均六跑12题次：raw为4 pass、7 partial、1 fail；V8为8 pass、4 partial。重复均保留。这只是有界题意主链的结果，**不是全事实或完整归因准确率**；已单列的V8实质错误仍否决联合验收，不可仅据core比例声称全正确。事实细项只定位缺口，不换算为这些核心判定。
