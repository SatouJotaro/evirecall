# 统一评测底座：使用与交接

已落实总计划中的 M1、M2 离线流程，以及 M3 接入准备工具。命令行支持 `fixture` 和显式 `module:factory_name` 后端；真实 Smurfs/Jev 实现仍由同伴交付。有限 pilot 清单与可核算的 judge 调用入口见 [M3 交接说明](pilot-handoff.md)。真实付费 pilot、主比较、证据预算与并发实验尚未运行，fixture 通过率只检查程序接线。

## 1. 运行与复算

需要 Python 3.11+，本机验证使用 Python 3.12。核心模块只使用标准库，无新增第三方依赖。在仓库根目录执行；Windows 可将 `python` 替换为 `.venv\Scripts\python.exe`。

```bash
python -m evirecall doctor
python -m unittest discover -s tests -v
python -m evirecall run --config configs/run-fixture.json --output runs/fixture-run
python -m evirecall score runs/fixture-run --expectations fixtures/evaluator/expectations.jsonl --output runs/fixture-evaluation
python -m evirecall summarize runs/fixture-run --evaluation runs/fixture-evaluation
```

所有输出目录必须是新目录。`run` 不读答案、不执行评分；`score` 当前是 fixture 评分器；LongMemEval 使用下面单独的官方评分导入/导出命令。`summarize` 仅读取已保存文件，不启动 agent 或 judge。原有 `smoke` 命令继续可用。

`configs/run-fixture.json` 是可执行的最小配置。任务路径相对配置文件所在目录解析。agent、memory、condition、重复编号和 history mode 均显式指定；未知 backend、配置键或非法限额在创建运行目录前拒绝。

| 产物 | 内容与用途 |
|---|---|
| `manifest.json`、`code/`、`tasks.jsonl` | 固定 task IDs、输入 hash、配置、Python/Git 信息和源码快照。dirty checkout 也保留实际执行代码 |
| `schedule.jsonl` | queued/started/skipped 以及未启动原因；任务排队时间自本批次开始计 |
| `results.jsonl` | 父进程逐题持久化的终止状态、预测、证据、时间和调用汇总 |
| `trace.jsonl`、`sources.jsonl` | 角色事件、不可变来源登记、group/session/task 关联；不包含 evaluator 答案 |
| `calls.jsonl` | 每次物理请求的 started/finished 事件、重试关联、阶段、模型和 usage |
| `stores/` | 每个独立 group/分支的实际存储目录；每个 run/condition/repetition 新建 |
| `execution.json`、`summary.json` | 批次耗时、全局停止原因、固定分母、调用覆盖率和离线汇总 |

逐条 JSONL 写入使用 flush + fsync。强制结束 worker 后检查 worker 写入的文件；发现未完成尾行就停止启动新 group，原始字节保留，复算时报告警告。内部损坏记录不会被静默跳过。此阶段不支持原目录追加恢复；重跑必须新建运行。

执行并发固定为 1。一个独立 group 在一个 spawn worker 进程内顺序执行，同组失败后停止其后续 session；其他独立 group 可继续。父进程监督任务/批次超时并终止 worker。该机制能停止本地 worker 的后续写入，不能撤回已经到达远端的请求或保证远端不再计费；live adapter 应避免另起后台服务，并使用 HTTP 超时。

## 2. 记账、评分与失败口径

资源账本以物理请求为单位，同一个 logical call 的重试有不同 call ID。`input_tokens`/`output_tokens` 是非负整数，费用是非负数；缺失值为 `null`。全部费用未知或部分未知时不输出伪造的总价，只输出 `known_cost_usd`、覆盖率和未知调用数。无请求时 `requests=0`，模型用量仍不假定可观测。

`ingestion`、`execution`、`evaluation` 分阶段聚合。离线评分不产生模型调用；新增 judge 入口使用独立 evaluator 运行目录和 `evaluation` 调用账本，其真实服务仍待配置。输出对象中旧的 `Usage` 字段不作为权威计账来源。

`max_calls` 是整个 run 的物理请求上限，含重试；`max_attempts` 是一个 logical call 的最大尝试次数。只重试 adapter 明确指定的异常，禁止 SDK 隐藏重试。`max_cost_usd=0` 在首个请求前停止；正值是基于已结算费用的下一次请求停止阈值，不能预测当前请求的最终费用，因此不是供应商硬额度。先前有未知费用时不再发下一次请求。正式 pilot 还需要供应商预算、请求数与输出长度上限。

汇总分别报告 planned、started、not_run、interrupted、completed、abstained、failed、scored、judge_error 和 unscored_valid。成功率下界 = 已知成功 / planned；上界加上有合法预测但尚无判分的题目。执行失败、未启动、进程中断不会变成正确拒答。已评分子集准确率与评分覆盖率单列。任何真实 LongMemEval 拒答都必须保存实际生成的非空文字；fixture 的空拒答仅供原有离线契约测试，不可导出为 benchmark 预测。

评分目录独立于执行目录，复算会校验结果 hash 与任务清单。已评分结果被改写后，旧评分不能继续用于汇总。

## 3. LongMemEval 数据

固定来源见 [数据锁](../configs/longmemeval-s.json)：官方 cleaned S revision `98d7416c24c778c2fee6e6f3006e7a073259d48f`，源文件 SHA-256 为 `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`。下载情况与实际审计结论见 [实施记录](implementation-status.md)。准备命令只处理本地文件：

```bash
python -m evirecall prepare-longmemeval data/raw/longmemeval/longmemeval_s_cleaned.json --revision 98d7416c24c778c2fee6e6f3006e7a073259d48f --sha256 d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442 --output data/processed/longmemeval-s
python -m evirecall split-longmemeval data/processed/longmemeval-s --output data/processed/longmemeval-s-split --dev-units 10 --test-questions 100 --seed 0
```

模型只接收 `public/tasks.jsonl`：中性的 task/source IDs、原始消息内容与角色、保持原顺序的历史、query 和原始日期。`answer_`/`_abs` 原始 ID、`has_answer`、gold answer、证据映射和 split audit 留在 evaluator 侧。原文中的正常内容不做字符串替换，以免改变任务。

源日期没有时区，`timestamp=null`、`source_time_raw` 保留原始文本；query 日期用 `query_time` 保留。没有伪造 UTC。中性 source ID 同时保留 session/turn 序号；真实 adapter 须使用这些边界组装 session，不能把每条 turn 当作独立 session。

原始数字答案保留为数字，仅位于 evaluator 侧。重复历史 session ID 按出现位置区分，映射同时记录 session/turn 序号；重复 question ID 仍拒绝。空历史消息与正文里的 Unicode 分隔符保留，JSONL 只按物理换行拆记录；空消息不能被 fixture 检索为支持答案的证据。生成的 public/evaluator/inventory 文件都有 hash，划分前检查一致性。

每个 QA query 有独立执行 group，避免上一题答案写回下一题。划分所用 `split_group_id` 与执行 group 不同：完整历史相同、问题家族相同，或任何证据会话在另一题历史中出现，都连接为同一划分单元。仅作为 filler 的共享会话只报告重叠，不强制合并。这里的 dev/test 是本项目本地划分，不是官方 S/M/oracle 划分。

`dev_units=10` 指连通组数，不一定是 10 道题；test 请求约 100 题时保留完整组，可能超过 100。实际数量、类别、跨集合重叠和不足标志写入 manifest。若出现巨型连通组导致没有可用 heldout，停止冻结正式划分，由团队选择并记录协议调整；不得回退为随机按题划分。

## 4. 官方评分封装

固定 upstream commit `9e0b455f4ef0e2ab8f2e582289761153549043fc` 的 [evaluate_qa.py](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py) 和 [print_qa_metrics.py](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/print_qa_metrics.py) 为规则来源。

```bash
python -m evirecall export-longmemeval RUN_DIRECTORY --references FROZEN_REFERENCES_JSONL --output runs/judge-inputs
python -m evirecall import-longmemeval runs/judge-inputs --scores OFFICIAL_RESULTS_JSONL --output runs/judge-replay
```

导出时恢复 evaluator 原始 question ID，预测格式为 `question_id` + `hypothesis`；错误/遗漏任务保留在 planned 分母中。导入只接受官方 `autoeval_label` 布尔结果及模型名，检查 ID 唯一性、覆盖、hypothesis 一致性和 artifact hash；不引入 exact-match 替代官方判分。

默认要求所有已导出预测都有评分；中断评分必须显式 `--allow-partial`，未知评分保留 unknown。输出包括六类得分、总体逐题平均、六类等权平均，以及非互斥的 abstention 子集；缺失类别时完整六类宏平均为 null。不同 judge model 混用会拒绝，其他单一模型会标记与官方 `gpt-4o-2024-08-06` 打印协议不兼容。官方标签解析规则原样保留，不能把它理解成新的可靠性验证器。

导入目录保存 `official-results.jsonl` 原始判分和 `inputs/` 输入副本，可在无 API、无原源路径的情况下重新导入复算。新增 `judge-longmemeval` 提供离线 `--check` 和显式配置后的调用入口，已通过 localhost 故障测试；真实 judge 服务和预算仍待确定。其账本、原子判分与费用限制见 [M3 交接说明](pilot-handoff.md)。工程测试的模拟标签不能作为真实实验结果。

## 5. 给两位同伴的接入契约

现有 `AgentBackend.run(task, memory, budget, emit)` 保留签名；新运行器传入可调用的 `RuntimeContext`，兼容原来的 `emit(role, operation, payload)`。公开 contracts 写入版本为 2，旧的带时区 Observation 和无 query_time 输入仍可读。新增字段是原始时间、memory store_path 和 repetition。

Xiaochen 的真实 agent/memory adapter 应满足：

- 只接收公开 `TaskInput`；`MemoryScope.store_path` 是唯一当前可写的记忆 namespace。`reset` 仅做本地初始化；网络摄入在绑定当前 context 后进行。
- 每次真实模型/记忆服务请求走 `context.call(...)`，传入 role、operation、phase、provider、请求模型名、usage 解析器和 `actual_model_fn`。将 HTTP timeout 限制到 `context.remaining_seconds` 内，SDK 自动重试设为零。
- 请求/提示内容若需要复现，由 adapter 保存脱敏文件；通过 metadata 的 `request_ref`、`request_sha256`、`prompt_template_sha256`、`price_ref`、`cache_policy` 记录引用。不要记录 API key、认证头或私密环境变量。
- 新工具观察先用 `context.register_source(Observation)` 登记再进入记忆。来源登记只证明可回查与 ID 不可变，不判断证据是否足以支持结论。
- 返回 `AgentOutput`，保留实际证据 source_ids，遵守 `max_items` 与 `max_characters`。字符数是 Python `len(text)`，不是 token 预算。方法内部有效性、原文回查和消融由 Xiaochen 实现。
- 通过 `module:factory_name` 显式配置新的 backend；不允许服务失败后回退到 fixture。关闭时释放资源；不额外创建不受监管的后台进程。

Bijun 的 STALE/MemoryArena adapter 应约定独立分支与跨 session 继承、可写回字段白名单、终止条件和 evaluator-only 字段；MemoryArena 的答案/奖励不得当作正常观察进入记忆。Chengyu 提供公共接口与故障夹具，不替代任务环境和可靠性标签的实现。

## 6. 后续验收门槛

M3：同伴提交一个可导入真实 backend；共同确认回答/judge/记忆服务和试运行预算；先 1 题闭环，再小规模 dev pilot，核对调用账本、真实 usage 与失效路径。

M4：先冻结可用的 heldout 与条件，然后分别运行证据预算轴、独立 group 并发轴。当前不提供并发 2/4、方法消融或资源曲线；这些不能由 fixture 速度推导。

M5：从真实已保存结果产生 CSV、图表和脱敏复现包，并由另一成员交叉复算/复跑。平台还未验证 Linux 行为，现有 CI 模板也尚未启用。
