---
name: create-task-agent
description: Guide a Personal Agent through copying and customizing a researcher-owned Task Agent definition.
---

# 建立一个 Task Agent

你是研究员的 Personal Agent。只修改 Agent 定义，不修改 Gateway、状态机、Worker Lease 或服务进程。

1. 复制 `agent-definitions/example-fast-agent-card.yaml` 到你的定义槽。
2. 修改 `name` 和 `instruction`，写清楚该 TaskNode 要完成的研究任务。
3. 只在 `allowed_domain_mcps` 中列出该任务允许使用的领域 MCP，例如 Research Mapping、LLM-Wiki 和中央草稿箱。
4. 按本机配置填写 `.env` 中的队列地址、消费者组、数据库路径、Worker 持久目录、领域 MCP 地址和草稿箱 MCP 地址。
5. 将修改后的卡片装入定义槽，然后让已常驻的 `gateway/mcp`、`gateway/subscriber` 和 Worker 模板读取它。
6. 用假上游交接运行最小验证，确认执行进入 `completed` 且保存 `draft_id`。

Gateway 进程、状态机、租约和服务启动方式由套件维护。关闭 harness 时不要停止两个 Gateway 进程；打开 harness 时只运行套件提供的检查 hook。
