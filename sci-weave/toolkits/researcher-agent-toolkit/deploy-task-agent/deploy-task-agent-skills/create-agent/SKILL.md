---
name: deploy-task-agent-create-agent
description: 创建或复制研究员端 Task Agent 定义。
---

# 创建 Agent

你是 Personal Agent，只编辑 Agent 定义文件。复制 `agent-definitions/agents/example-fast-agent.yaml`，修改 `name`、`instruction`、`model` 和允许的领域 MCP；不要编辑运行时、Gateway、Worker Lease 或服务模板。完成后将定义装入套件约定的定义槽，并交给验证技能检查。

先阅读 `references/agent-definition.md`，确认字段和边界。

安装位置与启动方式由套件维护者与 `install.sh` 决定（`~/.sciweave/task-agent`）；研究员侧只需要改 `.env` 与 Agent 定义，不要手工 `systemctl` 启停或改 `systemd/` 单元。
