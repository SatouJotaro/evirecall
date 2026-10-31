# 团队交接登记

观察日期：2026-10-31。本文记录当前 checkout 可见的交付与接入条件；“待交付”只表示本 checkout 尚未收到可验收产物，不推断负责人在其他分支或本机的实现进度。研究设计与分工以[执行计划](plan.md)为准，运行步骤见 [pilot 说明](pilot-handoff.md)，Git 操作见[协作指南](collaboration.md)。

## 首次真实 LongMemEval pilot 的门槛

先完成 X-01 至 X-03、C-01 至 C-03，再运行 1 题闭环并核对账本与独立评分。Xiaochen 交付真实 Smurfs/Jev 后端、factory、依赖、调用 hooks 和未加干预的 baseline；Chengyu 负责 runner、judge 配置、资源与结果复算。回答/记忆/judge 的模型、provider 与支出上限由三人共同决定，judge 的具体配置和资源操作仍归 Chengyu。

Bijun 的 STALE 公开输入/金标隔离、MemoryArena 工具与分组、错误案例可以并行交付；这些项目不阻塞首次 LongMemEval pilot。首次 pilot 不等于正式方法比较，也不代替后续任务验收。

## 可验收交付表

“分支 / PR / commit”必须填写真实定位信息；当前“待填”不代表远端没有分支。状态限定为：待交付、待评审、需修改、已验收、已集成。完成实现不自动变成已集成。

| ID | 负责人 | 必填具体值或产物 | 分支 / PR / commit | 验收条件 | 状态（2026-10-31） | 评审人 |
|---|---|---|---|---|---|---|
| X-01 | Xiaochen Bai | 真实 agent 与 memory 的 `module:factory_name`；实现路径、方法名称及未加干预 baseline 配置 | 待填 | 顶层零参数 factory 可导入；满足公共 contracts；导入/构造不请求服务；不回退 fixture | 待交付 | Chengyu Tang；Bijun Zeng 核对证据语义 |
| X-02 | Xiaochen Bai | Python 版本、固定依赖/上游 commit、安装命令、环境变量名、服务启动/健康检查步骤（不提交密钥） | 待填 | 新环境按步骤可安装并导入；Smurfs 与 Jev 各服务/模型依赖明确 | 待交付 | Chengyu Tang |
| X-03 | Xiaochen Bai | observe/retrieve/answer/write-back hooks；每次物理请求经过 `RuntimeContext.call`；baseline 的最小接入记录 | 待填 | 摄入、检索、回答及 Jev judgment 请求可追踪；无隐藏重试；来源 ID、隔离/reset 与未知 usage 语义可核查 | 待交付 | Chengyu Tang；Bijun Zeng |
| B-01 | Bijun Zeng | 小规模 STALE 转换产物、公开字段白名单、evaluator-only gold/解释、版本与 source IDs | 待填 | 公共任务无答案/冲突解释泄漏；固定样本可加载；官方评分与自定义评分区分 | 待交付；不阻塞 LME pilot | Xiaochen Bai；Chengyu Tang |
| B-02 | Bijun Zeng | 一个 MemoryArena travel 环境的数据库来源/版本与准备命令、工具 schema、权限、session/group/reset 规则、固定 group 清单 | 待填 | 可复现一个完整多 session group；模型只见合法观察；ground truth 独立保存；失败与环境限制明确 | 待交付；不阻塞 LME pilot | Xiaochen Bai；Chengyu Tang |
| B-03 | Bijun Zeng | update/no-update 配对案例、更新点与有效约束、来源引用、固定 trace、错误/恢复定义及独立 scorer 命令 | 待填 | scorer 不依赖真实 agent 即可运行；保留分歧与失败；注明官方任务或自定义压力案例 | 待交付；不阻塞 LME pilot | Xiaochen Bai；Chengyu Tang |
| C-01 | Chengyu Tang | runner/CLI/独立评分/账本、LongMemEval provenance、1/10 题 pilot manifest、复算命令 | `tangchengyu/evaluation-harness`；实现 commit `733b2a3`；PR 创建后补填 | Windows / Python 3.12：101 项测试通过；fixture 3/3、0 请求、汇总复算一致；数据与运行产物按文档在本地重建 | 待评审 | Xiaochen Bai；Bijun Zeng |
| C-02 | Chengyu Tang（选择由三人确认） | 回答、记忆及 judge 的 provider、endpoint、请求模型/版本、凭据环境变量名；价格来源、请求/费用/超时/重试上限 | 待填 | 所有具体值冻结；未知费用处理明确；非零支出有团队明确上限；judge `--check` 通过且不被误认为服务验证 | 待交付 | Xiaochen Bai；Bijun Zeng |
| C-03 | Chengyu Tang | 使用 X-01 的实际 run 配置、judge 配置、只读 preflight 输出及准备命令 | 待填 | 无占位 backend；源/任务 hash 一致；配置与依赖定位完整；零阈值模板不当作可付费配置 | 待交付 | Xiaochen Bai；Bijun Zeng |
| C-04 | Chengyu Tang | pilot-1 的 manifest、结果/trace、调用账本、judge 原始响应/判断、summary 与复算命令（敏感 evaluator 内容受限保存） | 待填 | 核对真实模型、完整摄入、usage 覆盖、unknown/失败与分母；独立复算一致后决定是否扩到 10 题 | 待交付；依赖首次 pilot 门槛 | Xiaochen Bai；Bijun Zeng |
| G-01 | 仓库管理员；Chengyu 提供检查命令 | 启用离线 CI；首次成功后为 `main` 配置至少一名同伴审查与实际检查名称 | 待填 | PR 上可见检查结果；分支规则实际生效；公共接口仍由相关负责人共同评审 | 待交付；不阻塞本地 LME pilot | 三人共同核对 |

## 更新与集成协议

1. 负责人在自己的 PR 中按 ID 更新本表，填写实际分支、PR 链接、commit、具体配置值或产物路径、复现命令、验收证据及未解决限制。只引用别人的口头进度不能标为交付。
2. 提交可验收产物后标“待评审”；评审人在 PR 中记录接受或需要修改的条目。公共 contracts、字段或跨模块语义变化须另外两位负责人共同评审。
3. Chengyu 在接入 runner 后，逐项写明集成目标 commit、使用的配置与检查结果，确认后才标“已集成”。评审通过但尚未合并/接入时保留“已验收”。
4. 每次更新保留观察日期；新环境缺少 ignored 的数据、vendor 或 runs 时，记录准备命令与 hash，不把文件缺失推断为他人没有工作。新阻塞注明依赖 ID、负责人和解除条件。

首次真实结果形成前，fixture/localhost 验证只证明工程接线，不能报告 benchmark 正确率、恢复收益或资源优势。
