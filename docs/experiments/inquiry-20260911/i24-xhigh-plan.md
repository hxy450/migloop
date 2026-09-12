# i24-xhigh：同一Luna、同一工具/指南，只改变复核深度

i23-high两题核心4/4，F10-04已恢复正确的后修鸿蒙行为观察；F10-07仍混合已观测onNewWant与未知桥键语义。本轮不加提示段落、不改schema/收集/检索/图边、不换更强型号。比较Luna high与xhigh，检验当前已可达证据下是否需要更多推理复核。

模型保持gpt-5.6-luna，唯一设置改变model_reasoning_effort=xhigh。[官方Luna说明](https://developers.openai.com/api/docs/models/gpt-5.6-luna)列出该深度。API/账号/权限/上下文设置不变，实际模型和effort仍核native turn_context。若失败或超时照实保留，不退回high补跑伪装成同组。

先跑F10-07，核心2/2且正确分开实际重入与未观测语义、无重大额外错误才跑F10-04；均通过后同冻结候选覆盖余八文件。沿用10题/28核心和原稳定性要求，无raw重跑、无自动重试、不选最好一次。不将effort收益归给代码或两原子结构，成本独立记录；这是开发集上的一次对照，不证明泛化。

不改既有iterate.py及其历史driver哈希。prepare函数本身接受effort，命令行prepare仅列medium/high，所以显式通过原函数建立独立目录；实际run仍使用原脚本：

```python
import runpy
driver = runpy.run_path('docs/experiments/inquiry-20260911/iterate.py')
driver['prepare'](driver['ROOT'] / 'i24-xhigh', effort='xhigh')
```

核对i23/i24冻结代码及每题prompt哈希相同，仅effort/settings不同。主文件修改仍只有用户自己的service.py及test_deveco_bare_id.py，不触碰。若此对照不能解决问题，再根据真实调用/原文交付决定下一步，不因失败就增加词法猜测或降低分数门槛。
