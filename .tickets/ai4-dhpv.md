---
id: ai4-dhpv
status: open
deps: []
links: [ai4-we38, ai4-353s, ai4-yvh2, ai4-gqj3, ai4-z3z4, ai4-te1v, ai4-csyj]
created: 2026-10-21T22:12:00Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-kpvp
tags: [wayfinder:grilling, agent, task-agent, centre-agent, mcp, message-queue]
---
# Agent 以消息驱动，Gateway 的 MCP 只负责返修

task-agent 与 centre-agent 都改由消息驱动：任务下发、上游交接、触发执行全部走消息队列。**这两个 Agent 的 Gateway 自己的 MCP 面**收窄为人工介入，即返修与观察。

## Question

确定 Gateway 的 MCP 与平台各领域 MCP 的分工、消息负责哪些动作、以及被推翻的既有结论如何处理。

## Design

### 两类 MCP，面向对象不同

这是本票最容易读错的地方，先说清：

| 类别 | 使用者 | 作用 |
| --- | --- | --- |
| **Agent Gateway 的 MCP**（task-agent、centre-agent 各自的） | 人（Owner、Project Owner，经自己的 harness） | 返修、验收、回答提问、观察。**不用于下发任务** |
| **平台领域 MCP**（Research Mapping、LLM-Wiki、Buffer） | Agent（端侧 task-agent、centre-agent） | Agent 干活的工具箱：读正式图、读写草稿、提交 candidate、读写候选 |

「MCP 只做返修」这句话只约束第一类。第二类 MCP 是 Agent 的能力来源，不受此限，而且正是端侧 Agent 与中央服务交互的主要途径。

### 为什么 Gateway 的 MCP 不承担下发

原设计把 Gateway MCP 当主通道：`submit_owner_command` 提交任务命令、首次执行由 Project Owner 调 MCP 触发。端侧自持之后有两个问题：

1. 它要求人的 harness 一直连着 Gateway，而任务下发本质上是异步事件。
2. 它把「下发任务」和「人工介入」混在同一张工具表里，两者的授权、幂等与审计要求不同。

消息驱动把两者分开：消息负责「有事发生」，Gateway MCP 负责「人要介入」。

### 职责切分

| 动作 | 走什么 | 说明 |
| --- | --- | --- |
| 上游交接就绪，触发下游首轮 | 消息队列 | 领域正式版本发布时发消息 |
| 根任务首次执行 | 消息队列 | 无上游，由 Project Owner 触发一条任务就绪消息 |
| Agent 读正式图、读写草稿、提交 candidate | 平台领域 MCP | 这是 Agent 的正常工作路径 |
| 执行中出现提问，等待回答 | Gateway MCP | `query_execution` 返回 `waiting`，人通过 MCP 回答 |
| 返修 | Gateway MCP | `review_execution(decision="request_revision")` |
| 验收、驳回、请求人工接管 | Gateway MCP | 同上，`accept` / `reject` / `request_human_takeover` |
| 取消 | Gateway MCP | `cancel_execution`，需单独确认是否归入「返修」 |
| 观察进度与待办 | Gateway MCP | 只读，`query_execution`、`list_pending` |

**不再通过 Gateway MCP 做的事**：提交任务命令、触发首次执行、下发上游交接。

### MCP 工具面保留，用提示词约束用途

`submit_owner_command` 这类工具**保留**，因为「返修要求」本身也是一条命令，需要一个结构化的提交入口。改变的只是它的用途边界：它是人向 Agent 下达处置要求的入口，不是任务下发入口。

首版通过提示词与工具描述约束 Agent 与人的使用范围，不做服务端硬性拒绝。若后续发现被绕过，再考虑在工具层收紧。

### 对 centre-agent 的对应收窄

centre-agent 也是消息驱动：草稿进入某状态、候选出现新 head 等事件由消息触发它去预审。它的 Gateway MCP 只暴露两件事：

- 查看预审结果。
- 要求重新预审某个候选。

「返修」这个词在 centre-agent 上不贴切，这里的语义是「对已完成工作的处置」，不是下发新任务。

## 被推翻的既有结论

以下票已关闭，结论仍然有效，但其中「Gateway MCP 下发任务」的部分作废。按仓库规则不修改原文，只在其上追加修订说明：

| 票 | 被推翻的部分 |
| --- | --- |
| `ai4-353s` Task Owner 通道与上游交接队列物理隔离 | `submit_owner_command` 作为**任务**提交入口 |
| `ai4-yvh2` 执行与接纳状态机融合及 Owner 审核工具边界 | `submit_owner_command` 作为任务输入路径的地位；`trigger` 取值中的 `owner_command` |
| `ai4-gqj3` ExecutionRecord 控制、审核与恢复 MCP 工具 | 「waiting 后靠 `submit_owner_command` 创建新执行」这一条 |
| `ai4-z3z4` 最小 Task Agent 项目组实现规格 | Owner MCP v1 协议中「命令即任务」的定位 |

仍然成立的部分：工具集合本身（`submit_owner_command` 保留但改用途）、`review_execution` 的四种决定、`query_execution` 的返回字段、`list_pending` 的排序与 `action_required`、幂等键语义、审计事件形状、Worker Lease 与串行化。

## Acceptance Criteria

- [ ] 明确两类 MCP 的分工：Gateway MCP 面的人工作业与领域 MCP 的 Agent 工作路径，两者不混用
- [ ] 明确消息负责的动作与 Gateway MCP 负责的动作，两者不重叠
- [ ] 明确 `submit_owner_command` 保留但用途收窄为返修与处置，且首版靠提示词约束而非服务端拒绝
- [ ] 明确根任务（无上游）的首次执行由什么触发
- [ ] 明确 centre-agent 在消息驱动下的触发事件与它的两个 Gateway MCP 动作
- [ ] 逐条列出被推翻的既有结论，并在对应票追加带日期的修订说明（不覆盖原文）
- [ ] 明确消息驱动下执行记录的 `trigger` 取值，不再包含 `owner_command`

## Notes

**2026-10-21T22:12:00Z**

来源：2026-10-21 第三轮讨论。原话要点：「我觉得有一个约束，就是 task-agent 和 centre-agent 都应该是消息驱动的，不应该由 MCP 交付其他任务，MCP 仅负责返修的要求」。

本票与「Task Agent 改由研究员端侧自持」的关系：后者定运行时归属与权限面，本票定通道分工。

**2026-10-21T22:35:00Z**

重要澄清（同日第四轮）。初版把「MCP 只做返修」写成对全平台 MCP 的约束，这是误读。Project Owner 原话：「我说的 MCP 只做返修是 centre-agent 和 task-agent 的 Gateway 的 MCP；wiki，buffer，map 后续也会有 MCP，这些可供 agent 调用的」。

据此改写：

- 新增「两类 MCP」一节，区分 Gateway MCP（人用）与领域 MCP（Agent 用）。
- `submit_owner_command` 由「作废」改为「保留但用途收窄」：返修要求也是命令，仍需要结构化入口。
- 约束手段由「服务端拒绝」改为「提示词与工具描述约束」，因为它们都在研究员或中央自己的部署里，硬拦意义有限。

待定：取消是否属于「返修」；根任务的首条消息由谁产生（PO 在 Web 看板上点，还是别的入口）。
