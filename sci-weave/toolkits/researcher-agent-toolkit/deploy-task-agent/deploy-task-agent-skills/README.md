# deploy-task-agent-skills

研究员端 Task Agent 技能组。每个短技能只加载自己的 `references/`，Personal Agent 只能修改 Agent 定义、工作流声明和资源配置。

## 技能

- `create-agent`：复制并填写 Agent 定义。
- `compose-workflow`：组合 Router、Orchestrator、Parallel 和 Agents as Tools。
- `configure-mcp`：选择标准或本地 MCP 资源并配置环境变量。
- `verify-task-agent`：用假上游消息和假草稿箱验证完整链路。
- `troubleshoot`：按边界定位配置、服务和工作流故障。

Personal Agent 不得修改 `runtime/`、Worker Lease、Gateway 或服务模板；打开 harness 只能执行 `hooks/check-services.sh` 的用户服务检查。关闭 harness 不停止用户级常驻服务。
