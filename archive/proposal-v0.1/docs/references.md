# 文献与软件来源

核对日期：2026-10-27。条目按 proposal 引用顺序排列。论文支撑研究论断；软件文档说明实现接口；上游论文中的结果不作为 EviRecall 的结果。

<a id="smurfs"></a>
## [1] Smurfs

Junzhi Chen, Juhao Liang, Benyou Wang. **Smurfs: Multi-Agent System using Context-Efficient DFSDT for Tool Planning.** NAACL 2025, pp. 3281-3298. DOI: 10.18653/v1/2025.naacl-long.169.

- [正式论文](https://aclanthology.org/2025.naacl-long.169/)
- [代码](https://github.com/FreedomIntelligence/Smurfs)
- 用途：执行底座、角色分工和上下文效率的研究来源。
- 边界：原论文任务与本项目拟用任务不同；迁移后的结果需重新评测。

<a id="tiermem"></a>
## [2] TierMem 论文

Qiming Zhu, Shunian Chen, Rui Yu, Zhehao Wu, Benyou Wang. **From Lossy to Verified: A Provenance-Aware Tiered Memory for Agents.** arXiv:2602.17913, 2026.

- [可核对的预印本](https://arxiv.org/abs/2602.17913)
- [作者仓库](https://github.com/FreedomIntelligence/Tiermem)
- [会议记录入口](https://openreview.net/forum?id=svKCa4itcd)
- 版本说明：仓库标题更新为 *TierMem: Balancing Compressed Memory and Raw Evidence for Long-Horizon Agent Memory* 并标注 COLM 2026。OpenReview 页面本次访问遇到浏览器验证；BibTeX 使用已核实的预印本，不混写成已核对的会议题录。
- 用途：摘要 / 原文分层、充分性路由和有来源的写回。
- 边界：论文版路由训练和 Jev 轻量应用分开描述，不移用论文指标。

<a id="jev"></a>
## [3] Jev TierMem 软件

FreedomIntelligence. **Jev TierMem: Lightweight Agent Memory.** Tiermem 仓库的软件文档与源码，访问于 2026-10-27。

- [介绍](https://github.com/FreedomIntelligence/Tiermem/tree/main/jev_tiermem)
- [Python 接入示例](https://github.com/FreedomIntelligence/Tiermem/blob/main/jev_tiermem/examples/README.md)
- 核对提交：`d0d3896e917117ba0fcc1501e2b2dae891d2a2e3`。
- 用途：记忆接口、provider 依赖、存储方式与具体接入约束。
- 边界：软件来源，不冒充独立同行评审论文；模拟 provider 检查不等于真实服务验证。

<a id="longmemeval"></a>
## [4] LongMemEval

Di Wu, Hongwei Wang, Wenhao Yu, Yuwei Zhang, Kai-Wei Chang, Dong Yu. **LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory.** ICLR 2025; arXiv:2410.10813。

- [论文](https://arxiv.org/abs/2410.10813)
- [代码及使用说明](https://github.com/xiaowu0162/LongMemEval)
- [清洗版数据](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned)
- 用途：记忆能力评测与证据会话标注。
- 边界：S/M/oracle 不是数据划分；目前推荐使用 V1 清洗版，不能把 V2 的不同任务与结果混入。下载时进一步固定数据 revision 和哈希。

<a id="memoryarena"></a>
## [5] MemoryArena

Zexue He et al. **MemoryArena: Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks.** arXiv:2602.16313，v2，2026。arXiv 记录标注 ICML 2026。

- [论文](https://arxiv.org/abs/2602.16313)
- [代码](https://github.com/ZexueHe/MemoryArena)
- [旅行规划环境](https://github.com/ZexueHe/MemoryArena/blob/main/setup_travel.md)
- [数据](https://huggingface.co/datasets/ZexueHe/memoryarena)
- 用途：记忆如何服务后续行动。
- 边界：仓库标为预览版，旅行环境需要另取大型航班 CSV；多会话 / 多人规划不是天然多 Agent。需固定环境和 judge / feedback 模式。

<a id="mast"></a>
## [6] MAST

Mert Cemri et al. **Why Do Multi-Agent LLM Systems Fail?** arXiv:2503.13657，2025。

- [论文](https://arxiv.org/abs/2503.13657)
- [作者代码与数据](https://github.com/multi-agent-systems-failure-taxonomy/MAST)
- 用途：错误分类与轨迹分析的方法参考。
- 边界：不同版本的数据规模有变化，不用早期摘要数字混写最终版本；MAST 不直接提供本项目所有“过期记忆传播”标签。

<a id="governed"></a>
## [7] Governed Shared Memory

Yanki Margalit, Nurit Cohen-Inger, Erni Avram, Ran Taig, Oded Margalit. **Governed Shared Memory for Multi-Agent LLM Systems.** arXiv:2606.24535，2026。

- [预印本](https://arxiv.org/abs/2606.24535)
- 用途：过期传播、矛盾与来源治理的近邻工作，帮助限定贡献范围。
- 边界：作者说明其评估侧重真实服务及架构发现，不直接提供与本方案相同条件的算法优越性结论。

<a id="deepagents"></a>
## [8] Deep Agents

LangChain. **Deep Agents overview.** 官方软件文档，访问于 2026-10-27。

- [文档](https://docs.langchain.com/oss/python/deepagents/overview)
- [代码](https://github.com/langchain-ai/deepagents)
- 用途：曾比较的工程底座、子 Agent 和上下文管理思路。
- 边界：本项目已选 Smurfs；该文档不是本项目方法贡献，也不引入第二个执行框架。

<a id="memoryagentbench"></a>
## [9] MemoryAgentBench

MemoryAgentBench authors. **Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions.** 此处引用作者代码仓库及数据说明，访问于 2026-10-27。

- [仓库](https://github.com/HUST-AI-HYZ/MemoryAgentBench)
- [数据](https://huggingface.co/datasets/ai-hyz/MemoryAgentBench)
- 用途：冲突消解等记忆能力的备选评测。
- 边界：完整集合含 LongMemEval 相关来源，不能将两者不加检查地当作独立训练 / 测试来源；如采用需固定具体子集并查重。

<a id="course"></a>
## [10] 2026 秋季课程要求

**CSC5051 / CSC6052 / MDS5110 Natural Language Processing, Fall 2026.** 课程网站，访问于 2026-10-27。

- [官网](https://nlp-course-cuhksz.github.io/)
- 用途：项目报告的动机、引用、技术方法、合理评测和个人贡献要求。
- 边界：官网最终报告页数不自动套用到 proposal；过去课件 / 春季模板中的日期不能直接当作本学期截止日期。正式模板、语言与最新截止以课程通知核对。

## 额外候选：LoCoMo

[作者仓库](https://github.com/snap-research/locomo) 提供长期会话数据。若最终转向直接复现 TierMem，可考虑它与 LongMemEval 的组合；两套会话问答不等于已完成交互行动评测。使用时按完整会话隔离，不随机拆同一会话的 QA。
