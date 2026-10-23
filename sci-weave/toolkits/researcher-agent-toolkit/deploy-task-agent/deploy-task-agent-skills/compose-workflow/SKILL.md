---
name: deploy-task-agent-compose-workflow
description: 组合同一 Worker 内的多 Agent 工作流。
---

# 组合工作流

在配置中声明 `Router`、`Orchestrator`、`Parallel` 或 `Agents as Tools`，并填写入口、子 Agent、汇总器和最终写入 Agent。子 Agent 共享一个平台级执行上下文，不创建自己的消费者、租约、ExecutionRecord 或草稿。

先阅读 `references/workflow-patterns.md`，选择最小模式；然后使用验证技能运行假消息。Personal Agent 只改工作流配置，不改 runtime 实现。