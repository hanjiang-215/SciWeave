# 中央 Agent 职责汇聚

从已有工单摘出中央 Agent 的职责，并记录 2026-10-21 讨论后的连续两次收窄。`centre-agents`、`buffer`、`registery` 都仍是空目录或只有说明。这里不增加新能力。

收窄的依据与推翻条目见 `centre-agent-scope-reduction.md`。旧工单 `ai4-vbnr`、`ai4-m0vt` 描述的调度、重试、转交、推进正式版本，本文件不再采纳。

## 只做一件事

**候选版本的预审与合并。** 只针对 Research Mapping 和 LLM-Wiki 的候选版本：格式、引用、权限、依赖、基准版本、冲突、影响范围，以及生成必要的混合候选。

工单里的中央 Agent 是一个 Agent，配置两套互相隔离的管理 MCP。它不通过一次提交同时改两个领域。

> 修订（2026-10-21）：原第一件事「部署 Task Agent」已删去。Task Agent 改由研究员端侧自持，中央不再部署、绑定或审核 agent 设计。依据工单「Task Agent 改由研究员端侧自持」。中央 Agent 由「做两件事」变为「只做一件事」。

## 不再负责

| 原职责 | 现在的归属 |
| --- | --- |
| 初始化研究地图、创建项目、指定节点负责人 | Project Owner |
| 调度与首次执行触发 | Project Owner 经自己的 MCP 触发 |
| 普通失败的重试、转交、人工接管 | 取消。归属未定 |
| PO 批准后推进正式版本 | Project Owner |
| 独立的人员与 Agent 注册服务 | 只保留按主体登记 MCP 能力的表，不再是中央 Agent 的职责 |
| 部署或托管 Task Agent | 取消。研究员在自己的电脑上自持其 agent |

## 不能做的事

- 不代替 TaskNode Owner 接纳执行结果。
- 不代替 Project Owner 批准正式路线、目标、依赖、激活条件、回滚或恢复。
- 不把候选、或仅被节点负责人接纳但尚未正式发布的内容送去调度。
- 不把 Mapping 和 Wiki 写进同一次提交或同一个 Proposal。
- 不替 Project Owner 在多个候选方案里做最终选择。
- 不部署、不安装、不重启、不托管研究员的 Task Agent，也不保存其模型凭据。
- 不写审计。留痕是固定工具，由 Buffer、两套管理 MCP 等写入方在写事实的同一事务里调用。

## 开发顺序

1. 一个进程，两套管理 MCP，分别只谈 Mapping 或 Wiki。
2. 从两套管理 MCP 读已存在的候选分支做预审；通过后生成必要混合候选，交 Project Owner 选择。
3. 不写正式版本，也不发起执行。

## 开发形态

已定的部分：`centre-agents` 是 `centre-control` 下的独立项目，一个 Agent，对外只通过两套互相隔离的管理 MCP 谈 Mapping 和 Wiki，自己不保存领域正文。

运行时（2026-10-21 讨论通过，尚未写进工单）：中央 Agent 用 `fast-agent-mcp` 做单实例常驻进程，不按任务类型复制多份 Agent。能力差异用 MCP 工具区分，不用多个实例区分。

> 修订（2026-10-21）：原「复用 `sci-weave/task-agent` 的 Gateway 代码，让同一组件组同时承担 MCP 入口和消息队列消费」作废。Task Agent 的 Gateway 已移到研究员端侧，与中央 Agent 分属不同部署单元、不同项目组。中央 Agent 如需进程骨架与审计写法，按需自建，不复用端侧代码。

需要注意的边界：中央 Agent 只对外暴露管理 MCP，不暴露 Owner 命令类工具，也不承担消息队列消费。

## 需要的套件

| 组成 | 内容 | 现状 |
| --- | --- | --- |
| Mapping 管理 MCP | 读候选、预审、生成混合候选 | `centre-control/research-map` 在实现 |
| Wiki 管理 MCP | 同上，但只谈 Wiki | `centre-control/research-wiki` 在实现 |
| 候选预审入口 | 经两套管理 MCP 读取已存在的候选分支、回写预审结论 | 依赖 `research-map` / `research-wiki` 暴露候选读接口 |
| 草稿箱 | 中央 Agent 不进草稿箱；一审由人在 `centre-control/buffer` 完成 | `centre-control/buffer` 未实现，契约见 `draft-buffer.md` |
| 留痕工具 | 固定接口，由写入方在写事实的同一事务里调用 | 未实现，必须先于其他写入方落地 |
| 技能 | 预审清单；候选对比与混合 | `toolkits/centre-agent-toolkit` 只有标题 |

这套件里不该出现的：直接写正式图的工具、代替 Project Owner 批准的工具、发起执行或调度 Worker 的工具、一次调用同时改 Mapping 和 Wiki 的工具、部署 Task Agent 的工具。

## 对应工单

| 能力 | 工单 |
| --- | --- |
| 留痕工具（写入方统一调用） | ai4-upsm |
| Buffer 取件与候选预审入口 | ai4-he04 |
| 预审检查项与失败处置 | ai4-5z9e |
| 草稿箱存储与审核契约 | ai4-xem8 |
| 候选方案合成与送审 | ai4-oebi |
| 能力接口收口 | ai4-rlv6 |

## 已关闭

- `ai4-8k4y` 调度与可修复失败：中央 Agent 不再承担调度。
- `ai4-8ybr` 正式版本推进：改由 Project Owner 经自己的 MCP 完成。
- `ai4-25wy` 消息队列事件入口：其中「执行进入待接纳」「已接纳」「已批准」等触发事件随调度一并取消。
- `ai4-s12u` 部署 Task Agent 绑定：Task Agent 改由研究员端侧自持，中央不再部署。
