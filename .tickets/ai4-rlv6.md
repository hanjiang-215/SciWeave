---
id: ai4-rlv6
status: open
deps: [ai4-he04, ai4-5z9e, ai4-oebi]
links: [ai4-upsm]
created: 2026-10-21T12:16:16Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, centre-agents, interface]
---
# 中央 Agent 能力接口收口

在各项能力定稿后，收口中央 Agent 的对外接口形态：进程常驻形态、工具命名与分组、鉴权、以及它调用 Buffer、两套管理 MCP、留痕工具的方式。

## Design

运行时方向见 docs/data-flow/centre-agent.md：fast-agent-mcp 单实例常驻，能力用 MCP 工具区分而非多实例。Gateway 的 MCP 面只承担返修与处置，不承担任务下发。

本票晚于各能力票，因为它要收口的是已经定下来的能力，不是预先猜测的接口。

> 修订（2026-10-21）：原「复用 task-agent 的 Gateway 骨架与租约、审计写法」作废。task-agent 的 Gateway 已随任务负责人部署，与中央 Agent 分属不同部署单元，不再共用代码；中央 Agent 如需进程骨架，自建。

## Acceptance Criteria

- 工具清单与各能力票一一对应，无重复无遗漏
- 鉴权与调用者标识有明确来源
- 明确中央 Agent 没有任何写审计的私有通道
- 明确 Gateway 的 MCP 面只承担返修与处置，不承担任务下发；任务由消息驱动


## Notes

**2026-10-21T12:48:25Z**

2026-10-21 修订：中央 Agent 职责收窄后，本票只需收口两条线——部署 Task Agent，以及候选版本预审与合并。调度、失败处置、消息队列入口、正式版本推进均不在范围内，对应票已关闭。

> 更正（2026-10-21T22:42:00Z）：「部署 Task Agent」这条线已随端侧自持取消，本票只剩**一条**收口线——候选版本预审与合并。相应依赖 `ai4-s12u` 已在同日关闭。

**2026-10-21T13:18:41Z**

2026-10-21T21:20:00Z

边界变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)。本票 Design 中「复用 task-agent 的 Gateway 骨架与租约、审计写法」这一条作废：

- Task Agent 的 Gateway 移到研究员自己的电脑上，与中央 Agent 分属不同部署单元、不同项目组，不再共用代码。
- 中央 Agent 如需进程骨架与审计写法，自建即可，不再引用端侧实现。
- 中央 Agent 只对外暴露管理 MCP，不暴露 Owner 命令类工具，也不承担消息队列消费。

仍然成立的收口项：工具清单与各能力票对应、鉴权与调用者标识来源、没有写审计的私有通道。另新增一项：按主体登记 MCP 能力的校验由「端侧 Agent 的 MCP 能力注册与限制」(ai4-ujvn) 定义，本票需说明中央 Agent 自身的工具是否参与该校验。

**2026-10-21T14:36:24Z**

2026-10-21T22:42:30Z

依赖调整：解除对「中央 Agent 按已批准绑定部署 Task Agent」(ai4-s12u) 的阻塞依赖。该票已于 2026-10-21 关闭，且其立意（中央部署 Task Agent）已随端侧自持取消。本票其余依赖不变。
