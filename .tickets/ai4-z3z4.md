---
id: ai4-z3z4
status: open
deps: []
links: [ai4-yyy9]
created: 2026-10-19T07:07:36Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [spec, gateway, fast-agent]
---
# Gateway MVP 与最小 fast-agent 技术规格

将 Gateway 与最小 fast-agent 执行闭环的 Wayfinder 决策整理为可实现的技术规格。该规格是实现 tickets 的唯一上游输入，不包含 Research Mapping MCP、Agent Kit 或 ZIP 交付。

## Design

## Problem Statement
仓库已有 fast-agent-mcp 外部 Worker 启动、固定会话恢复和端侧 Gateway 边界决策，但尚无产品代码入口。需要建立最小 Gateway，使 Owner 能提交受控命令，平台能持久化执行状态并按需启动短生命周期 Worker，完成一次 fast-agent loop。

## Solution
实现一个 Python 常驻 Gateway：使用标准库 HTTP 作为最小 Owner 请求入口，使用 SQLite 保存 TaskSession、OwnerCommand、ExecutionRecord 和 AuditEvent，使用本地进程调度器按 task_node_id 串行启动 Worker，使用 Runtime Adapter 调用 fast-agent-mcp。Worker 使用平台生成的固定 session_id、专属持久 home、connection scope 和 session history；执行完成后保存结果并退出。

## Public seams
- Owner Command submission：提交 task_node_id、命令内容和幂等键，返回 command_id、execution_id 和初始状态。
- Execution query：按 execution_id 查询当前状态、结果摘要、错误摘要和 session 标识。
- Cancellation：按 execution_id 请求取消，返回取消请求结果；已完成执行不可取消。
- 健康检查：返回 Gateway 可接受请求和本地存储可用状态。

## Domain objects and state
- TaskSession：每个 task_node_id 一个稳定 session_id；状态 active、waiting、cancelled、failed、completed。
- OwnerCommand：幂等键唯一；状态 accepted、running、succeeded、failed、cancelled。
- ExecutionRecord：每次实际 Worker 尝试一条不可变记录；状态 created、running、waiting、succeeded、failed、cancelled。
- AuditEvent：追加记录命令接收、状态迁移、Worker 创建/退出、运行时结果、取消和错误摘要。

## Runtime and persistence
Gateway 核心只依赖 Runtime Adapter、Execution Store 和 Worker Scheduler。首版适配器分别为 fast-agent Runtime Adapter、SQLite Store 和本地进程 Scheduler。Gateway 在一个 SQLite 事务中创建 OwnerCommand、ExecutionRecord 初始记录和命令审计事件，然后调度 Worker。重复幂等键返回既有命令及其结果，不创建新的执行。

Runtime Adapter 至少支持 run、resume 和 cancel；同一 task_node_id 不能同时有两个 Worker。Worker 以固定 session_id 恢复 fast-agent Harness，会话 home 必须持久化。默认关闭自动 compaction。运行时异常、超时、非零退出或会话无法恢复时，ExecutionRecord 失败并保存错误摘要；Gateway 重启不自动重做已失败执行。

## Authentication and configuration
首版只支持本地开发令牌配置；真实令牌通过环境变量或本机安全配置注入，不能写入仓库。首版不实现多租户权限、远程 A2A、Redpanda、EventBus 或领域 MCP。

## Testing decisions
测试通过上述 HTTP 公共 seam 验证外部行为，不检查私有实现。必须覆盖：健康检查、首次命令提交、幂等重复提交、执行状态查询、Worker 成功、运行时失败、取消、同一 task_node_id 串行化、Gateway 重启后的会话恢复，以及使用 passthrough fast-agent 的最小运行时集成测试。真实模型凭据不进入测试。

## Out of scope
Research Mapping MCP、依赖图、Agent Kit/Skills/Hooks、ZIP 交付、跨服务器部署、Redpanda 上游交接、完整 A2A Human Input、真实模型提供商接入和生产级自动恢复。

## Acceptance Criteria

- [ ] HTTP 公共 seam、对象状态和 SQLite 持久化规则明确且可实现。
- [ ] 一次 Owner Command 能产生可查询的 ExecutionRecord 和 AuditEvent。
- [ ] 相同幂等键不会创建第二个执行。
- [ ] Worker 能通过 fast-agent Runtime Adapter 完成一次 loop 并释放。
- [ ] 固定 session_id 能在新的 Worker 中恢复。
- [ ] 失败、取消、串行化和 Gateway 重启读取行为有自动化验证。
- [ ] 规格未引入 MCP 领域逻辑、Agent Kit 或 ZIP 交付。

## Notes

**2026-10-19T08:53:34Z**

关联 Gitee Pull Request #9：https://gitee.com/qi-yueran/ai4science/pulls/9（目标 develop）。PR 包含 Gateway MVP 基础闭环、技术栈约束与实现路线图；后续实现票仍按依赖图推进。
