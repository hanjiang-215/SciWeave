---
id: ai4-s12u
status: closed
deps: [ai4-upsm]
links: [ai4-he04, ai4-5z9e, ai4-oebi]
created: 2026-10-21T12:47:16Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, centre-agents, task-agent, deployment]
---
# 中央 Agent 按已批准绑定部署 Task Agent

Project Owner 审核通过负责人的声明式设计后，中央 Agent 写入 Agent 身份与绑定记录，由 Gateway 在既有的 task-agent 容器里按该绑定拉起短生命周期 Worker。部署不等于启动。

## Design

依据 docs/data-flow/task-agent-binding.md 与 2026-10-21 讨论：设计字段为已注册模板、任务指令、允许列表中的模型、允许列表中的 MCP 引用、是否保留会话历史。缺字段或越界的方案不得部署，中央 Agent 不补设计、不执行负责人提交的代码。

身份记录只引用 principal_id，人先登记，Agent 记录在绑定审核通过后才写入。密钥和令牌不入库。部署不新建容器、不新占宿主机端口、不复制源码。

待定：部署接口形态（Gateway 新工具还是独立 MCP）、绑定与身份表的列、重复部署同一节点的处置。

## Acceptance Criteria

- 只接受带 Project Owner 批准记录的方案
- 缺字段或引用允许列表之外的模型/MCP 时拒绝部署
- 部署只写身份与绑定，不启动 Worker
- 同一节点重复部署有明确语义
- 部署结论经留痕工具记录


## Notes

**2026-10-21T12:48:25Z**

2026-10-21：本票取代 ai4-8k4y 与 ai4-25wy 中「部署完成后通知」的部分。设计字段、身份表与部署语义见 docs/data-flow/task-agent-binding.md，职责收窄依据见 docs/data-flow/centre-agent-scope-reduction.md。

**2026-10-21T13:07:55Z**

2026-10-21T21:06:00Z

本票立意被推翻，关闭。依据「Task Agent 改由研究员端侧自持」(ai4-we38)：中央不再有 task-agent 服务，研究员在自己的电脑上编写和运行 agent，自己启动、自己重启。因此「按已批准绑定部署」的三个前提全部消失——没有绑定表、没有部署动作、没有中央拉起 Worker。

原正文保留供追溯。本票涉及的设计字段、身份表、重复部署语义不再需要实现；其中「按主体登记可用 MCP 能力」的最小替代由「端侧 Agent 的 MCP 能力注册与限制」(ai4-ujvn) 承接。
