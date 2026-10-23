---
id: ai4-o2n3
status: closed
deps: []
links: [ai4-cdia, ai4-za77, ai4-x6gd, ai4-eikj, ai4-mx7h, ai4-83uk, ai4-99ut, ai4-jbci]
created: 2026-10-23T02:24:13Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [spec, ready-for-agent, task-agent, work-agent, multi-agent, fast-agent, skills, toolkit]
---
# 研究员端侧 Task Agent 与 deploy-task-agent-skills 规格

形成一份面向研究员端侧的完整 Task Agent 规格，统一已有 Work Agent 运行时、研究员套件、deploy-task-agent-skills 技能组、标准与自定义资源，以及一个 Worker 内部的 fast-agent 多 Agent 工作流。

该规格复用最小 Work Agent 实现规格和已完成实现票的结论，不重新设计消息驱动、ExecutionRecord、Worker Lease、草稿箱和 Centre Agent 的既有边界；新增内容聚焦研究员端侧技能组、Agent 定义、Agent 资源库、MCP 资源库和 Router/Orchestrator/Parallel/Agents as Tools。

一个平台级 Work Agent 对应一个 Worker、一个 ExecutionRecord 和一个最终 draft_id。多个内部 Agent 属于同一 fast-agent 工作流，不单独取得消费者组、Worker Lease 或平台级 ExecutionRecord。

## Design

## Problem Statement

研究员可以运行一个最小 Task Agent，但现有规格分散在 Work Agent 运行时、研究员套件和后续技能组工单中。套件目前只有运行时、服务壳、单张 Agent 卡片和基础技能，缺少统一的 Agent 定义、工作流、Agent 资源、MCP 资源和多 Agent 组织规格。

## Solution

建立一份统一规格：保留消息驱动的三组件运行时，在一个短生命周期 Worker 内支持 fast-agent 多 Agent 工作流；提供名为 deploy-task-agent-skills 的技能组，使用多个短技能与各自 references；平台提供标准 agent-libs 与 mcp-libs，研究员通过 local-agent-libs 与 local-mcp-libs 扩展；最终写入 Agent 负责创建唯一草稿并返回 draft_id。

## User Stories

1. 作为研究员，我希望复制一个 Agent 定义并替换任务指令，以便创建自己的 Task Agent。
2. 作为研究员，我希望通过技能选择允许的领域 MCP，以便不用修改运行时源码。
3. 作为研究员，我希望用 Router 将不同类型任务交给不同子 Agent，以便复用同一入口。
4. 作为研究员，我希望用 Orchestrator 拆分和汇总研究任务，以便完成复杂任务。
5. 作为研究员，我希望并行运行相互独立的子 Agent，以便缩短执行时间。
6. 作为研究员，我希望把子 Agent 作为主 Agent 的工具调用，以便复用专业能力。
7. 作为维护者，我希望多 Agent 工作流仍只有一个平台级 ExecutionRecord，以便状态和审计保持可理解。
8. 作为维护者，我希望最终写入 Agent 产生唯一 draft_id，以便草稿和执行记录可关联。
9. 作为 Personal Agent，我希望按技能组中的 references 获取详细规则，以便每次只加载当前任务需要的知识。
10. 作为研究员，我希望在标准资源之外增加本地 Agent 和 MCP 资源，以便适配自己的研究领域。

## Implementation Decisions

- Task Agent 继续采用消息队列触发、ExecutionRecord、Worker Lease、短生命周期 Worker 和草稿箱 MCP 的既有 Work Agent 架构。
- `runtime` 负责状态机、租约、幂等、Worker 调度和执行结果；`service-template` 负责三个进程角色的装配和启动。二者职责分离，但作为同一套件交付。
- Agent 定义是配置数据，独立于 `agent-libs`；Agent 工作流可以作为定义中的结构化声明或独立工作流资源，但必须有稳定 schema。
- `agent-libs` 提供提示词、任务模式、校验器、结果格式化器和工作流资源。
- `mcp-libs` 提供 Research Mapping、LLM-Wiki、草稿箱等 MCP 的工具目录、调用说明、示例和配置约定。
- `deploy-task-agent-skills` 是技能组，拆分创建 Agent、组合工作流、配置 MCP、验证 Task Agent 和排障等技能；每个技能可以携带独立 references。
- 第一版支持 Router、Orchestrator、Parallel、Agents as Tools。它们都运行在同一个 Worker 内。
- 子 Agent 不单独取得消费者组、Worker Lease、ExecutionRecord 或最终草稿身份。
- 最终写入 Agent 负责合成结果并调用草稿箱；一个平台级执行最终只产生一个 draft_id。
- 平台提供标准资源；研究员可以通过 local-agent-libs 和 local-mcp-libs 增加自定义资源。标准资源与自定义资源的加载、覆盖和版本规则需要在本规格中明确。
- 技能文本是行为约束和操作指导，不宣称其本身构成服务端权限边界；MCP 调用仍需具备可观察的调用记录。

## Testing Decisions

测试只验证外部行为，不检查 fast-agent 私有类、内部表结构或工作流实现细节。使用三个最高层接缝：

1. 假队列消息接收：验证 ExecutionRecord、Worker Lease、幂等和同目标串行。
2. Worker 工作流：使用 passthrough 或假运行时验证单 Agent、Router、Orchestrator、Parallel 和 Agents as Tools。
3. 草稿箱 MCP：使用假草稿箱验证最终写入 Agent 生成唯一 draft_id，并在写入成功后完成执行。

已有 Gateway MCP、Worker Runtime Adapter、研究员套件运行时测试作为测试先例。测试不依赖真实队列、真实模型、真实草稿箱或固定端口。

## Out of Scope

- 多 Worker 分布式多 Agent 编排。
- 子 Agent 独立的消息队列消费者组、Worker Lease、ExecutionRecord 和草稿审核状态。
- Agent Kit ZIP 交付、跨服务器安装和生产部署。
- 服务端强制执行技能文本中的全部行为规则。
- 新的领域 MCP 服务实现；本规格只定义客户端资源和调用约定。
- Research Mapping、LLM-Wiki 和草稿箱的领域内部数据模型。

## Further Notes

已有 `ai4-z3z4`、`ai4-cdia`、`ai4-za77` 和已完成 Work Agent 实现票是本规格的输入。规格完成后应继续拆分为实现票，而不是直接扩大已关闭工单。


## Notes

**2026-10-23T03:19:19Z**

2026-10-23：本规格实现链路完成。子票 ai4-x6gd、ai4-eikj、ai4-mx7h、ai4-83uk、ai4-99ut、ai4-jbci 均已实现并关闭。最终交付 runtime/service-template 边界、Agent/workflow 配置校验、agent-libs、mcp-libs、单 Worker 四类多 Agent 工作流、deploy-task-agent-skills 技能组和假消息到唯一 draft_id 的端到端验证。
