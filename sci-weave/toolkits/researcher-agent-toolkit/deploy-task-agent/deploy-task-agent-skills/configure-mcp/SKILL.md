---
name: deploy-task-agent-configure-mcp
description: 配置 Task Agent 的标准和本地 MCP 资源。
---

# 配置 MCP

只在 Agent 定义的允许列表和 `.env` 中配置资源。先阅读 `references/mcp-resources.md`，再选择最小资源集合；不要在源码中写地址、端口或令牌，也不要让 Personal Agent 修改 MCP Gateway。

验证时使用描述符注册表和假资源，不连接真实 MCP 服务。