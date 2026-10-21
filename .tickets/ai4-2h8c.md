---
id: ai4-2h8c
status: in_progress
deps: [ai4-m96w]
links: []
created: 2026-10-20T07:46:47Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, task-agent, ready-for-agent]
---
# fast-agent Runtime Adapter 与固定会话恢复

## Parent

最小 Task Agent 项目组实现规格（ai4-z3z4）。

## What to build

Worker 通过实际 fast-agent Runtime Adapter 和不需真实模型凭据的 passthrough 运行时，使用 TaskNode 的固定 session_id 与持久 home 完成首次执行及新进程恢复。

## Acceptance Criteria

## Acceptance Criteria

- [ ] fast-agent 依赖在项目组清单和唯一锁文件中声明，并在票据 Notes 记录来源、用途、版本约束、许可证或限制和验证命令。
- [ ] 首次 Worker 使用固定 session_id、持久 home、connection scope 和 session history 完成一次 passthrough loop。
- [ ] 新短生命周期 Worker 可用同一 TaskNode 会话完成后续一次恢复执行；不同 TaskNode 不共享会话。
- [ ] 默认关闭自动 compaction，Worker 每次 loop 后退出并保留受配置控制的会话文件。
- [ ] fast-agent 故障、会话恢复失败和持久目录不可用均形成可查询 failed 执行和无敏感信息审计。
- [ ] 集成测试不使用或保存真实模型凭据。

## Notes

**2026-10-21T02:46:38Z**

2026-10-21：已确认并声明 fast-agent-mcp 运行时依赖。来源：PyPI fast-agent-mcp 0.10.46；用途：Worker 的实际 fast-agent Runtime Adapter 与无真实模型凭据的 passthrough loop；版本约束：>=0.10.46,<0.11；许可证：Apache-2.0。该包要求 Python >=3.12,<3.16，故项目组三个 Python 子项目的 requires-python 已同步收紧。验证：cd sci-weave/task-agent && uv sync；uv run --package sciweave-task-agent-worker python -c "from fast_agent.core.fastagent import FastAgent; print(FastAgent.__name__)"（输出 FastAgent）；uv run --package sciweave-task-agent-gateway-mcp python -m unittest discover -s gateway/mcp/tests -v（17 passed）。

**2026-10-21T04:03:24Z**

2026-10-21：为 DeepSeek 官方 API 的本地人工验证增加 Worker 专属配置边界。新增 worker/.env.example：DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL、SCIWEAVE_WORKER_MODEL、SCIWEAVE_WORKER_HOME、SCIWEAVE_WORKER_SESSION_DIR、SCIWEAVE_WORKER_CONNECTION_SCOPE；真实 worker/.env 不提交。源码仅接收 uv --env-file 注入的环境变量，不自行读取 .env，且不会在结果或日志输出密钥。验证：占位 API Key 被 Worker CLI 拒绝；临时非敏感配置通过 uv run --env-file <temp> --package sciweave-task-agent-worker sciweave-task-agent-worker；Gateway MCP 20 passed、源码编译和 git diff --check 通过。后续由开发者填写本地 worker/.env 后，接入真实 DeepSeek loop。
