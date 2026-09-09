# V9：让声明单位适配证据，而不是用版本坐标硬装事件

2026-09-09 20:12 UTC预记，候选尚未运行。V8完整队列继续，不抹掉其失败或混成V9成绩。

## 由开发反馈得到的假设

V8首rep七文件的总token相对同题raw两rep均值，池化减少27.1%、文件等权平均减少20.8%，但Member尾后事件错挂末版、Splash遗漏真实候选脚本效应，仍未满足联合标准。这只是首rep观察，第二rep尚在运行，不能报告为完整稳定结果。C3与Dice反而更贵。

新假设：将“条目针对的文件”“正式版本状态”“未立版本但有原文的事件”“未调查补集”拆开，可减少为适配图和schema而造坐标、宽repair、重复清单的压力；把这些费用省下来是否改善真实上游调查，需要模型实验检验，不能由测试通过推出。

## 组合候选，不声称单因素消融

- 显式migloop-verdict/2；v1严格解析和旧报告保留，不重写历史文稿。GUIDE可用MIGLOOP_VERDICT_VERSION=1选旧契约，默认新产出为2。
- defect.target_file仅做模型声明的文件作用域，不创建文件版本、repair、读写边。recommendation是独立模型建议，保留在findings，不从散文猜补。
- event_claims用完整action引用定位。系统提供真实owner/事件外壳/实际effect_version或null/前一效应上下文与时间可用性；模型不能指定anchor/version。事件不是第三种图原子，不把上下文节点染红，不产生访问/读写边；失败、pending、文本自述分开。红节点与红事件都需basis，但字段齐全不证明其原因真。
- coverage采用全manifest摘要+少量reviewed行+not_investigated补集。摘要绑定账本、文件、政策、顺序与原事件身份；非法/重复行仍失败，不能被补集吞掉。declarations_complete只说逐项声明齐全，complete只说机械交代，语义未认证。
- 页面分开作用域、历史repair、事件主张、真实路线、已核读写。原文点击不换根；当前查看器展开不冒充模型当时所见。
- 查询两原子定义、读写解析、默认调查窗口不变；没有为具体题目填入答案、关键词或进入点。尚未增加独立reviewer模型。

## 运行与判定

继续使用原十题/七文件作为开发回归，GPT-5.5 medium/native，工具reference，1800秒。每文件两rep，Member/C4/Dice/Splash/C1/C2/C3顺序两遍；与其他队列合计最多两次调查并发。若出现实现故障，保留失败另版，不能在冻结源上改。

原始基线为formal-v6-document中Member/C4两rep、formal-v7其余五文件两rep。题目、池、模型设置相同；新runner仅按当前GUIDE声明schema，不把v1硬写进提示。所有成本是完整调查input_total+output（cache/reasoning不重复计），附uncached、wall/e2e及重复波动。

语义按protocol v1的核心/部分/失败与固定原文逐条审。false引用、无依据作者/时间/行为认证是关键错误；保守遗漏仍计部分，不以“未知多”冒充准确。期望10/10核心无关键错误；在实际样本中正确率优于raw且成本20–30%减少、UI无伪边/伪访问，才考虑联合目标成立。

新五题仍按holdout-v3-preflight执行：H3-P1因部分提前暴露只作附录，其余四题结果在候选冻结前不读。下一步是否让此候选进入留出，先看开发结果并另记决定；留出解盲后不能继续称未见测试。
