---
name: deploy-task-agent-verify-task-agent
description: 验证 Task Agent 的消息、Worker、工作流和草稿箱行为。
---

# 验证 Task Agent

先阅读 `references/e2e-checklist.md`，再在 runtime 目录运行测试。验证必须使用内存队列、假 Agent、假草稿箱和系统临时资源，不使用真实队列、模型、MCP 或固定端口。确认假上游消息经过 subscriber 和 Worker，完成多 Agent 工作流，并产生唯一 `draft_id`。

打开 harness 时只运行 `hooks/check-services.sh` 检查用户级服务；关闭 harness 不停止它们。