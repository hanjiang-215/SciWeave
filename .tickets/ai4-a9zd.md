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
