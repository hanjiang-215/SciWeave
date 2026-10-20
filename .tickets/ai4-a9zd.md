---
id: ai4-a9zd
status: open
deps: []
links: []
created: 2026-10-19T02:49:23Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-ufqu
tags: [wayfinder:prototype]
---
# 验证 fast-agent-mcp 外部进程与 A2A 启动路径

## Question
通过隔离的草稿测试，验证在项目 .venv 中以外部子进程启动 fast-agent-mcp，以及经 A2A 服务调用 fast-agent-mcp，是否都能完成最小 Agent 执行。测试脚本仅放在 drafts/，不修改产品源码或添加项目依赖。

## Acceptance Criteria

在 drafts/ 中提供可重复运行的测试脚本；记录两条路径的启动命令、实际结果、限制与清理方式；使用项目 .venv 执行；不提交凭据、模型配置或产品代码。


## Notes

**2026-10-19T02:57:21Z**

验证完成：在项目 .venv 中以 uv pip editable 安装 drafts/osp 的 fast-agent-mcp 0.10.46 后，drafts/fast-agent-startup-test/run_startup_tests.py 成功验证两条启动路径。外部子进程通过 Harness API 使用 passthrough 模型回显 external process message；本地 A2A 服务由 fast-agent start_server(transport=a2a) 启动，fast-agent CLI A2A 客户端成功收到 A2A owner message。两条路径均不需要模型凭据。限制：仅验证启动和最小文本响应，不验证产品消息队列、鉴权、Buffer、审计或真实模型。

**2026-10-19T03:03:47Z**

本原型的验证结论已纳入“Task Agent 运行时与套件接入方案”及“Task Owner A2A Gateway 与上游交接队列物理隔离”的前沿：外部短生命周期 Worker 与 A2A 服务调用均可启动 fast-agent-mcp；A2A 服务端应位于常驻 Gateway，而不是一次性 Worker。

**2026-10-19T05:31:59Z**

2026-10-19 A2A 输入/恢复能力验证：在 drafts/osp 使用 `uv run --frozen pytest -q tests/integration/a2a/test_fast_agent_a2a_server.py -k "input_required_task_for_follow_up or cancel_task_cancels_running_agent or research_intake_can_refine_or_start_task"`，结果为 3 passed。fast-agent-mcp 0.10.46 的 A2A 服务端会把 Agent 返回的 `LlmStopReason.PAUSE` 映射为 A2A `TASK_STATE_INPUT_REQUIRED`；客户端保留 task/context 标识，并可在同一任务中发送后续消息使其完成。取消运行中 A2A task 的用例也通过。

限制与后续：`human_input=True` 的默认实现调用本地交互 UI 回调，当前没有证据表明它会自动经 A2A 转发给远程 Codex。该 A2A 原型只保留为 fast-agent-mcp 的协议能力证据；SciWeave Owner 通道已决定采用 MCP（Streamable HTTP），不实现 A2A input-required 或 A2A 回调桥接。远程 Human Input 由 Gateway 的 `query_execution` 返回 `waiting` 和问题文本，Owner 通过同一 `execution_id` 提交新的 OwnerCommand 续接。
