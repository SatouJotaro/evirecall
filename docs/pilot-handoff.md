# M3：真实 pilot 的接入与运行

本轮交付的是可接入、可检查、可核算的工具。观察日期：2026-10-31；当前 checkout 尚未收到可验收的真实 Smurfs/Jev adapter、模型服务配置或支出上限，因此没有运行真实 benchmark。这是本 checkout 的交付状态，不推断同伴在其他分支或本机的实现进度。逐项交付、评审和集成状态见[团队交接登记](team-handoff.md)，分支与 PR 操作见[协作指南](collaboration.md)。

## 同伴拉取后的离线验收

先按[协作指南](collaboration.md)切到实际交付分支。在仓库根目录使用 Python 3.11 或更新版本（团队默认 3.12）运行：

```bash
python -m unittest tests.test_cli tests.test_pilot -v
```

这条短验收命令覆盖 fixture 执行→独立评分→离线汇总，合成 LongMemEval 转换/划分→有限 pilot→预测导出→judge 配置检查→完整及部分评分回放，并检查 hash、隔离和篡改拒绝。它使用仓库内的合成样本与固定官方评分源码，不需要 vendor、真实数据、模型服务、凭据或下载，不发起 HTTP 请求。临时输出在测试结束后清理。

成功标准是 11 项测试均显示 `OK`；测试中的零费用 judge 配置应报告 `ready=false`、`judge_calls_performed=false`，这是预期的阻止调用行为。fixture 与手写判分只用于接线验收，不是模型正确率。完整发布检查仍使用 `python -m unittest discover -s tests -v`；完整测试中的 judge 传输场景仅连接本机测试服务。

## 已准备的任务清单

```text
data/processed/longmemeval-s-pilot-1/
data/processed/longmemeval-s-pilot-10/
```

二者来自现有开发集，seed=0，每个受保护 split group 最多选 1 个 query；选择仅依赖 ID 和固定随机种子，不看答案、题型或结果。1 题清单是 10 题清单的首题。原开发集 327 题和测试集 102 题不移动、不缩减。

| 清单 | query 数 | 历史 observation 数 | 历史字符数 |
|---|---:|---:|---:|
| pilot-1 | 1 | 537 | 471,389 |
| pilot-10 | 10 | 4,942 | 4,858,423 |

这些是原始历史的字符计数，不是 tokens、模型输入窗口或费用估计。单题也包含大量摄入工作，不能依据 query 数假设费用很低。先接入 1 题，核对摄入/检索/回答的调用数，再决定是否扩到 10 题。清单用于工程 pilot，不代替正式 heldout 比较，也不保证六类题型或拒答覆盖。

重新生成到新目录：

```bash
python -m evirecall prepare-pilot data/processed/longmemeval-s --split data/processed/longmemeval-s-split --output data/processed/pilot-new --max-questions 1 --seed 0
```

工具检查所有源/划分文件 hash、任务清单、组完整性及 public/evaluator 内容一致性。请求超过可用开发组数会报错，不会自动扩大到整个开发集。所有输出附带源 manifest、划分 manifest 和内容 hash。

## Xiaochen 的后端交接

公共配置现在支持 `fixture` 或明确的 `module:factory_name`，例如 `team_adapters.smurfs:make_agent`。这些示例名字是占位符，不是已经实现的模块。factory 必须是可导入的顶层函数/类、可零参数调用，并返回满足公共接口的实例；构造和模块导入不应发起服务调用。实际模型参数由同伴 adapter 与团队协议约定。

`configs/run-pilot.template.json` 提供现成任务路径、独立 QA 分支和有限请求数；后端名字、condition 与费用阈值需要用实际交付配置替换。模板 `max_cost_usd=0` 表示不允许发出计账请求，不代表已经批准任何费用。每次真实 provider 请求仍须经 `RuntimeContext.call`，避免 SDK 隐藏重试。

```bash
python -m evirecall preflight --config configs/run-pilot.template.json
python -m evirecall run --config PATH_TO_CONFIGURED_RUN_JSON --output runs/real-pilot-1
```

模板第一次 preflight 报缺少 `team_adapters` 是预期结果；不会回退到 fixture。`preflight` 读取配置、任务和 factory 身份，报告历史大小与源码 hash，不构造 backend、不生成运行目录。它会导入你显式指定的可信 Python 模块，所以 adapter 必须避免导入副作用。

每次 run 保存实际 factory 实现模块的源码副本；重新导出的 factory 会定位到真正实现模块。源码副本不等于完整第三方依赖树，外部 adapter 的依赖版本仍需冻结。传给 `execute_tasks` 的程序化 callable instance 仍可用；配置入口仅接收顶层函数/类，以免预检查触发对象反序列化/构造。

## Chengyu 的 judge 入口

先从真实执行结果导出独立 evaluator 输入：

```bash
python -m evirecall export-longmemeval runs/real-pilot-1 --references data/processed/longmemeval-s-pilot-1/evaluator/references.jsonl --output runs/real-pilot-1-judge-inputs
python -m evirecall judge-longmemeval runs/real-pilot-1-judge-inputs --config configs/judge-pilot.template.json --check
```

`--check` 只校验本地输入与配置，报告凭据是否存在；不发送 HTTP，不创建输出，不验证账号权限或模型可用性。模板引用官方固定 judge 名称，保留零费用阈值；它不是服务可用性或价格承诺。密钥只放到配置指定的环境变量，本工具不自动加载 `.env`，不接受配置内的明文密钥。

填好实际服务、模型与费用/请求限额后，实际执行使用独立的输出参数：

```bash
python -m evirecall judge-longmemeval runs/real-pilot-1-judge-inputs --config PATH_TO_CONFIGURED_JUDGE_JSON --output runs/real-pilot-1-judge
```

`--check` 与 `--output` 二选一。实际 judge 采用显式 endpoint；HTTPS 使用指定环境变量中的 key，HTTP 只允许字面 loopback 地址供本地服务测试。无自动重定向、无隐藏 SDK 重试。正常 HTTPS 请求遵守本机代理设置，loopback 测试直连。

提示由固定官方源文件中经 hash 校验的纯函数生成，不导入其 SDK 依赖。保持官方 `n=1`、`temperature=0`、`max_tokens=10` 与原始标签解析规则。接受已核对的 LF/CRLF 两种文件字节 hash，记录实际源码 hash；源码与 MIT 许可随 evaluator 产物保存。其他请求/实际模型会在结果中体现，不能静默替代为另一模型后仍宣称完全遵循官方 judge 设置。

judge 输出目录为 evaluator-only：包含答案的请求和输入不能交给回答 agent 或记忆模块。每次物理调用记入 `execution/calls.jsonl`；原请求、响应、逐题原子判断和官方兼容结果均保留，原执行预测不被修改。已完成判断可独立回放；网络错误、超时或被限额阻止的题目保持 unknown，不填充错误答案。硬超时只能停止本地 worker，无法撤销远端已受理请求。

没有价格表时 token 用量可记录，美元费用为 unknown；在有限费用阈值下，先前未知费用会阻止下一次调用。429 也不自动视为免费，所以重试次数是上限，费用停止规则优先。可选 `pricing` 包含 `source`、`input_usd_per_million`、`output_usd_per_million`，仅得到声明价格下的估计，不是供应商账单；出现无法正确计价的缓存用量时仍保持 unknown。不要为了让批次继续而把未知价格填成零。

输出目录拒绝覆盖，不自动断点续跑。若实际返回的模型混杂，已保存原始数据会保留，但官方结果聚合拒绝将不同 judge 模型合在同一分数中。

## 本次之后的真实接入条件

首次真实 LongMemEval pilot 需要 Xiaochen 提供真实 Smurfs/Jev backend、可导入 factory、固定依赖/服务准备步骤、逐调用 hooks 和未加干预 baseline 的分支/PR/commit。回答服务、记忆服务、judge 模型/provider 和小规模支出上限由三人共同确定；Chengyu 负责实际 run/judge 配置、资源准备与核算。Bijun 的 STALE 公开输入/金标隔离、MemoryArena 工具/分组及错误案例并行交付，不阻塞该 LongMemEval pilot。然后先执行 pilot-1，核对完整摄入成本、实际模型版本、usage 覆盖、失效与评分状态。此次工具实施和 localhost 测试没有形成任何真实任务正确率、错误恢复收益或资源优势结论。
