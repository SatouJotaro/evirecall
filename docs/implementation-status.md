# 统一评测实施记录

实施记录日期：2026-10-30；交接状态观察更新：2026-10-31。基于 Chengyu 已确认的总计划，评测交付分支为 `tangchengyu/evaluation-harness`，实现 commit `733b2a3`（PR 状态见[交接登记](team-handoff.md)），起点 `bf15a708eba891d5d9eeae5ba7918b45c6c1481e`。本轮没有修改提案、实现同伴负责的方法或运行付费实验。使用说明见 [evaluation-harness.md](evaluation-harness.md)。

## 阶段状态

| 阶段 | 本轮结果 | 尚需满足的门槛 |
|---|---|---|
| M0 协议 | 公共 contracts v2、任务隔离、来源登记、调用账本和失败分母形成可审阅实现 | Xiaochen/Bijun 共同评审实际 adapter 交接语义；Chengyu 的计划确认不代替两人的接口验收 |
| M1 运行底座 | 显式配置、串行 group worker、超时终止、逐题结果、逐调用账本、独立评分与离线复算通过离线验收 | 首个真实 backend 接入后再验收 provider timeout、usage 与远端取消边界 |
| M2 数据与评分 | 完整 LongMemEval S 校验、500 题加载、分组审计、候选清单、官方输入导出与已保存判分回放完成 | 正式实验清单仍需团队冻结 |
| M3 小规模真实闭环 | 已准备 1/10 题候选 pilot、显式 backend/preflight 与有界 judge 调用工具；真实闭环尚未运行 | 可导入真实 backend、回答模型/记忆服务/judge、服务凭据与试运行费用/请求上限 |
| M4 主比较/资源实验 | 尚未运行 | M3 测量有效，冻结方法条件、具体预算档位、重试规则和实验清单 |
| M5 报告与复现包 | 离线复算入口和交接说明已提供 | 真实实验 CSV/图表、报告结果和同伴交叉复现 |

## 第一批实现的验证（M1/M2）

- Python 3.12.0 / Windows 上全量 `python -B -m unittest discover -s tests -v`：**68 项通过**。原有 12 项测试继续通过。
- 新增故障覆盖：成功请求后任务崩溃、显式重试、未知费用、硬超时、worker 退出、损坏尾行、独立分支隔离、零费用阈值、评分失败独立保存、预测改写后拒绝旧评分。
- 数据与评分覆盖：语义 ID 与嵌套标签隔离、日期保真、证据被复用为 filler 时的分组、实际数据格式、artifact hash、重复/遗漏评分、非空拒答、类别平均和完整分母。
- 修复了复核发现的证据跨集合问题、进程中断后追加损坏日志问题，以及模型元数据解析失败导致已知费用丢失的问题；均有回归用例。
- `git diff --check` 通过。尚未验证 Linux，也未启用 GitHub Actions。

已保存三条 fixture 的实际命令行产物：

```text
runs/m1-integration-20261030/
runs/m1-evaluation-20261030/
```

三题均保存终止结果（2 completed、1 abstained），fixture 检查 3/3，物理模型请求 0。重新读取保存文件得到与评分时完全相同的 summary。这些数据只证明工程闭环；fixture 吞吐和通过率没有模型或记忆机制的实验含义。

## 完整数据审计

官方 cleaned S revision `98d7416c24c778c2fee6e6f3006e7a073259d48f` 已完整下载，277,383,467 bytes，SHA-256 `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` 匹配。未采用第三方镜像。原始和派生文件保存在 Git 忽略的本地目录：

```text
data/raw/longmemeval/longmemeval_s_cleaned.json
data/processed/longmemeval-s/
data/processed/longmemeval-s-split/
```

全量 500 个 `TaskInput` 可加载，共 246,750 条 observation，其中 12 条空消息保真保留。原始答案有 468 个字符串、32 个整数；历史有 13 次重复 filler session ID，答案证据 ID 没有多位置歧义。重复会话按 ordinal 映射，不改变 source 文本或评分答案。

当前保守的历史/证据/家族连接规则产生 122 个划分组，最大的 5 个组分别含 314、9、6、5、5 题。seed=0、dev_units=10、test_questions=100 的候选划分结果如下：

| 题型 | 全量 | 开发集 | 测试集 | 未使用 |
|---|---:|---:|---:|---:|
| single-session-user | 70 | 50 | 13 | 7 |
| multi-session | 133 | 90 | 20 | 23 |
| single-session-preference | 30 | 15 | 11 | 4 |
| temporal-reasoning | 133 | 99 | 23 | 11 |
| knowledge-update | 78 | 39 | 22 | 17 |
| single-session-assistant | 56 | 34 | 13 | 9 |
| 合计 | 500 | **327** | **102** | 71 |
| abstention 子集（非互斥） | 30 | 25 | 3 | 2 |

完整历史、受保护证据、问题家族跨集合重叠均为 0；仅作为 filler 的共享 session hash 有 2,222 个，已显式记录，不能称为所有会话完全不重叠。开发集和测试集都覆盖六类，但样本不是独立同分布的随机题目切分；统计时仍要考虑 group 相关性。

**10 个开发单元实际包含 327 题，不能直接当作小规模 pilot 批量执行。** 大连通组进入开发集后仍保留 102 题 heldout，因此没有放宽既定隔离规则。后续实施已按固定 seed、每组最多 1 个 query 生成 1/10 题候选 pilot，均尚未运行真实模型；真实执行仍需先核对摄入成本与预算。没有运行整个开发集，也没有依据方法结果选择题目。

## 评分器与环境

已在 `vendor/longmemeval/` 准备并核对官方 commit `9e0b455f4ef0e2ab8f2e582289761153549043fc`，工作区干净。核对了 `evaluate_qa.py` 与 `print_qa_metrics.py` 的输入、模型映射、拒答分支和标签语义。没有安装或执行其付费模型调用逻辑。

2026-10-30 的环境检查中，`doctor` 确认 Python 与 SQLite FTS5 可用；该次观察没有 `.env`，真实 API 未测。其余五个 vendor checkout 在该环境缺失；早期文档提到的 `../library/` 也不在该环境。源码准备脚本可以恢复固定版本源码，但这不等于同伴 adapter、任务环境或服务可用。

状态只表示当前 checkout 可验收的交付，不推断同伴的其他分支或本机进度。后续交接按[团队交接登记](team-handoff.md)记录负责人 PR、commit、验收证据和 Chengyu 的集成确认；Git 操作见[协作指南](collaboration.md)。首次真实 LongMemEval pilot 依赖 Xiaochen 的实际 backend/factory/依赖/hooks/baseline，以及 Chengyu 的服务、judge 和预算配置；Bijun 的 STALE/MemoryArena 交付不阻塞该 pilot。后续交接仍按三人分工：Xiaochen 交付真实 agent/memory backend 及逐调用 hooks；Bijun 交付 STALE/MemoryArena 的公开观察、评分隔离和任务语义；Chengyu 负责运行、评分、费用核对和实验复现。尚未有任何真实 benchmark 正确率、恢复收益或资源优势结论。

## 后续实施：M3 工具准备

详见 [M3 交接与运行说明](pilot-handoff.md)。新增：

- `prepare-pilot`：校验源/划分 hash、完整组和内容一致性，从 dev 中选定有限 query。已生成 `longmemeval-s-pilot-1`（首题 `lme-q000375`）与 `longmemeval-s-pilot-10`。前者有 537 条历史、471,389 字符；后者有 4,942 条历史、4,858,423 字符。这些不是 token 或费用估计。
- 显式 `module:factory_name` 后端和 `preflight`：可信模块只导入、不构造 backend；限制配置为顶层函数/类，防止反序列化在检查时触发实例构造。实际实现模块与 hash 纳入运行快照。
- `judge-longmemeval`：固定官方提示/参数/标签规则，独立 evaluator 目录、物理请求账本、原始响应、逐题原子判断及父进程汇总。`--check` 无网络；真实调用需显式 endpoint、环境变量凭据与限额。工具已用 localhost 模拟服务验证，没有调用外部模型。
- 评分清单在请求前验证分母和 episode 一致性；最终协议标志同时考虑请求与实际返回模型。未知费用不会按零费用处理。源码快照和 judge 归档保留官方 MIT 许可。

`configs/run-pilot.template.json` 的同伴 backend 名称是占位符，`configs/judge-pilot.template.json` 记录官方 judge 模型。两者费用阈值都为 0；它们没有批准真实支出，也没有验证该模型当前可用。接下来等待实际 adapter 与服务/预算信息，再执行 1 题真实闭环。

本批次最终验收：Python 3.12 / Windows 全量 **99 项 unittest 通过**（63.946 秒），`git diff --check` 通过；两个 pilot 的 4 个内容 hash 和前缀一致性复核通过，10 题对应 10 个不同受保护组。真实 backend 模板的 preflight 如预期拒绝不存在的同伴模块。localhost 是传输与故障测试环境，不是模型 benchmark；该批次验收时尚未执行任何外部模型调用或正式实验；Git 发布状态另以实际 PR/commit 为准。

## 2026-10-31 发布前验收

重新验证并修复了 worker 日志末条 JSON 完整但未写入换行的恢复边界：保留原始记录并报告警告，停止启动后续 group，避免追加时拼接损坏日志。记录层与 runner 两项回归先复现问题，修复后通过；全量 **101 项 unittest 通过**（Windows / Python 3.12.0，71.133 秒）。独立 fixture 执行、评分和离线复算得到 3/3 检查通过、0 次物理请求、汇总完全一致；结果位于本地 ignored 的 `runs/publication-fixture-20261031` 与 `runs/publication-evaluation-20261031`。

提交范围检查排除了 `.env`、数据、vendor、运行日志和临时文件。官方 evaluator 的暂存 blob SHA-256 与固定上游一致，原始空白与 MIT 许可保留。此次检查仅覆盖本地 Windows 环境，未启用远端 CI、验证真实模型服务或形成 benchmark 结论。团队交付与管理员后续工作见[交接登记](team-handoff.md)。

实现与交接文档已推送至 `tangchengyu/evaluation-harness`，以 [Draft PR #1](https://github.com/SatouJotaro/evirecall/pull/1) 待评审，尚未合并 `main`。随后在提交 `d75576f` 的全新本地克隆中执行 `python -m unittest tests.test_cli tests.test_pilot -v`，**11 项通过**（14.054 秒）。该克隆无 `.env`、vendor、data、runs 或虚拟环境，验证了接入/评分/pilot 短验收无需这些外部交付；命令和预期结果已补入 [pilot 说明](pilot-handoff.md)。真实 backend、服务配置和预算的交接门槛保持不变。
