---
id: ai4-eikj
status: closed
deps: [ai4-x6gd]
links: [ai4-o2n3]
created: 2026-10-23T02:28:34Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-o2n3
tags: [implementation, ready-for-agent, task-agent, work-agent, toolkit, multi-agent, fast-agent]
---
# Agent 定义与工作流配置模型

## Parent

研究员端侧 Task Agent 与 deploy-task-agent-skills 规格（ai4-o2n3）。

## What to build

提供 Agent 定义和工作流配置的可加载模型与校验。定义至少表达 Agent 身份、指令、模型、允许使用的 MCP 资源和可复用资源；工作流至少表达入口 Agent、子 Agent、工作流类型、结果汇总者和最终写入 Agent。支持 Router、Orchestrator、Parallel、Agents as Tools 四种类型的合法示例，并拒绝循环引用、缺入口、缺最终写入 Agent 和未知资源。

## Blocked by

- 分离 Work Agent runtime 与套件服务模板（ai4-x6gd）

## Acceptance Criteria

- [ ] 合法 Agent 定义和工作流配置能够加载并产生稳定的配置对象。
- [ ] 四种工作流类型各有可验证的最小示例。
- [ ] 缺少入口 Agent、最终写入 Agent、子 Agent或引用资源时返回稳定配置错误。
- [ ] 循环引用和未知工作流类型被拒绝。
- [ ] 配置变化不改变运行时状态机、Worker Lease 或服务启动接口。
- [ ] 测试不依赖真实模型、真实 MCP 或固定部署地址。

## Notes

**2026-10-23T02:51:30Z**

2026-10-23：完成 Agent 定义与工作流配置模型。新增 AgentDefinition、WorkflowDefinition、TaskAgentConfig、load_config 和稳定 ConfigError；支持 Router、Orchestrator、Parallel、Agents as Tools，并校验缺入口、缺最终写入 Agent、未知引用和循环。验证：runtime 8 tests passed，git diff --check 通过。
