---
id: ai4-c61f
status: open
deps: []
links: []
created: 2026-10-26T18:38:14Z
type: bug
priority: 1
assignee: hanjiang
tags: [bug, centre-control, centre-agents]
---
# centre-agents 静默降级：配置错误与缺 API Key 都表现为「成功」

gateway/mcp 的 cli.py 捕获 ValueError 后把 settings 置 None，而 .env.example 缺 SCIWEAVE_WORKER_CONNECTION_SCOPE，导致 worker runtime 永不存在、执行永远停在 queued 且无日志。subscriber 缺 DEEPSEEK_API_KEY 时退回 FastAgentPassthroughRuntime，只写 history.json 并返回 completed，执行记录带假摘要。

## Acceptance Criteria

配置异常必须记 error 日志，并让 /health 报 worker_runtime: misconfigured。|补齐 .env.example 缺失的变量。|passthrough 运行时需显式开关，否则 require_api_key 校验 fail fast。|补测试覆盖两条路径。

