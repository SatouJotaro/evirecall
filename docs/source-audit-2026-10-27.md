# 来源与可行性核对：2026-10-27

核对目的：为 proposal 中的 Smurfs / Jev 接入设计提供可定位依据。本文不表示 EviRecall 已集成或已完成 benchmark。

## 源码版本

- Smurfs：`0f5c44701f6c9e5ac9caed9edc4ce16ad9c430c3`，已有本地参考检出。后续实施前应与选定上游版本对齐，不自动把本地快照当作最新发布。
- Tiermem：`d0d3896e917117ba0fcc1501e2b2dae891d2a2e3`，本次下载的参考检出。

## 关键代码依据

- [Smurfs worker](https://github.com/FreedomIntelligence/Smurfs/blob/0f5c44701f6c9e5ac9caed9edc4ce16ad9c430c3/Smurfs/inference/smurfs_worker.py)：非流式 `smurfs_worker`、规划入口、工具调用、日志与验证步骤。
- [Smurfs verifier](https://github.com/FreedomIntelligence/Smurfs/blob/0f5c44701f6c9e5ac9caed9edc4ce16ad9c430c3/Smurfs/agents/verifier_agent/verifier.py)：`run(question, answer, query_id)`，尚无独立证据参数。
- [Smurfs memory 文件](https://github.com/FreedomIntelligence/Smurfs/blob/0f5c44701f6c9e5ac9caed9edc4ce16ad9c430c3/Smurfs/agents/memory_agent/memory_agent.py)：核对快照为零字节。
- [Jev system](https://github.com/FreedomIntelligence/Tiermem/blob/d0d3896e917117ba0fcc1501e2b2dae891d2a2e3/jev_tiermem/system.py)：`observe`、`add_summary`、`retrieve`、`promote`、provider 注入与返回结构。
- [Jev store](https://github.com/FreedomIntelligence/Tiermem/blob/d0d3896e917117ba0fcc1501e2b2dae891d2a2e3/jev_tiermem/store.py)：SQLite FTS5、Markdown 笔记、来源校验及写锁。
- [Jev providers](https://github.com/FreedomIntelligence/Tiermem/blob/d0d3896e917117ba0fcc1501e2b2dae891d2a2e3/jev_tiermem/providers.py)：独立 Jev 判断服务、普通文本模型服务、失败状态和用量计数。
- [Jev config](https://github.com/FreedomIntelligence/Tiermem/blob/d0d3896e917117ba0fcc1501e2b2dae891d2a2e3/jev_tiermem/config.py)：字符和轮数预算。

## 已完成的离线核验

在上述 Tiermem 提交、Windows / Python 3.12 下运行作者现有测试：

```bash
python -X utf8 -m unittest jev_tiermem.tests.test_memory
```

结果：**26 项测试通过**。测试使用模拟 provider，覆盖记忆存储与管线行为；不是 Jev 服务或 EviRecall benchmark 的实测。首次沙箱运行因 Windows 临时目录权限报错；在获得所需本地权限后按相同测试命令通过。未修改上游源码以规避失败。

## 尚未完成

- Smurfs 与 Jev 的真实端到端连接。
- Jev 凭据、服务可用性、模型版本、用量和价格核对。
- MemoryArena 环境部署及 Smurfs policy 适配。
- 数据集下载、revision / 哈希固定、正式划分及任意性能实验。
- 候选更新机制实现、自然语言冲突检测与恢复正确性验证。

## 解释边界

论文、代码、离线测试、端到端运行和 benchmark 结果属于不同证据层次。离线测试通过支持“部分接口行为可用”的判断，不支持任务成功率提升、成本下降或生产可靠性结论。
