---
id: ai4-ru15
status: open
deps: []
links: []
created: 2026-10-16T00:37:28Z
type: epic
priority: 1
assignee: SciWeave
tags: [wayfinder:map, product, ai4science]
---
# 动态科研协作平台需求地图

## Destination
形成一个面向科研团队的动态科研协作平台宏观规格：支持多人和多个 AI Agent 围绕可演化的研究路线图共同规划、执行、共享资源、提交变更提案并完成负责人审计。此阶段只确定产品边界和一级功能，不进入技术栈、数据库、消息队列或具体实现。

## Notes
领域：通用科研 Agent 协作平台。
工作方式：研究路线图驱动任务，Agent 与人共同执行，公共资源沉淀，中央协调 Agent 处理提案，项目负责人承担最终审计责任。
参考方向：DeepScientist、Dify、n8n、LangGraph、AutoGen，以及现有相似产品调研。

## Decisions so far

- [平台定位与用户边界](ai4-9f7i.md)：平台服务一个科研小组及其项目，采用一名管理员和若干成员的简单组织方式；平台定位为通用科研任务控制平面，负责路线图、调度、审核、资源共享和审计，不开发具体科研领域能力或新的通用 harness 框架。研究人员可以接入自己的 personal-agent harness；平台提供的独立研究 Agent 使用轻量化、可配置的任务 harness。
- [多人和多 Agent 协作执行](ai4-e257.md)：任务节点可以由单人、多人、Personal Agent、轻量任务 Agent 或协作集合负责；Agent 处理重复和结构化工作，研究人员负责实验、判断、头脑风暴、路线维护和全部审计；Agent 结果须经负责人审核后才能进入公共资源，研究路线变化通过 Proposal 更新动态研究图。
- [科研路线图与动态研究图](ai4-ebqx.md)：项目只维护一张完整 Research Mapping，拓扑只包含统一的 TaskNode；节点保存自身信息，依赖和执行语义只由边保存；资源由独立资源系统管理并通过引用关联，展示通过视图筛选主图。

## Not yet specified

- 首个可演示科研场景和第一阶段产品范围。
- 公共资源、证据、版本和可复现记录的范围。
- Proposal / PR、中央协调 Agent 和负责人审计机制。
- 节点和边的版本管理、失败路线、动态变更和执行痕迹如何表达。
- 第一阶段最小产品范围与验证方式。

## Out of scope

- 当前阶段不确定具体编程语言、框架、数据库、消息中间件或部署方案。
- 当前阶段不实现完整科研平台、公开 Agent 市场或真实实验设备控制。

## Acceptance Criteria

完成宏观需求地图；每个一级功能域都有明确的产品决策票；明确当前范围、未决问题和暂不涉及的实现细节。
