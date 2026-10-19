---
id: ai4-gq0k
status: closed
deps: []
links: []
created: 2026-10-19T06:47:28Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# Gateway MVP 状态模型与端口边界

承接 Gateway 最小底座与 Agent Kit 交付地图；本票只解决一个实现前置决策，不直接编写产品代码。

## Design

## Question
最小 Gateway 与 `fast-agent-mcp` 执行闭环需要哪些核心对象、状态转换、幂等与审计事实？需要明确 Gateway、Worker、Runtime 和 Storage 之间的端口/适配器边界，以及首版可以使用的本地实现。MCP 领域服务、Redpanda 上游交接和 ZIP 交付不在本票范围内。

## Acceptance Criteria

形成可直接交给实现的 Gateway MVP 状态模型和端口边界；覆盖 Task Session、Owner Command、Execution Record、AuditEvent、Worker 生命周期、一次 Agent loop、固定会话恢复、失败/取消和同一 TaskNode 会话串行化。


## Notes

**2026-10-19T07:06:23Z**

Resolution（2026-10-19）：Gateway MVP 采用 Python 常驻进程作为平台入口，首版使用 MCP（Streamable HTTP）入口与 `sqlite3` 持久化，避免在最小闭环阶段引入额外 Web 框架依赖。Gateway 的公共 seam 是 Owner Command 提交、Execution 查询、取消请求和健康检查；认证首版使用本地开发令牌配置，不能写入仓库。

> 修订（2026-10-19）：原 Resolution 写的入口是“Python 标准库 HTTP”。Owner 通道改为 MCP 后，标准库 HTTP 保留为回环健康检查与测试 seam，Owner 主通道是 MCP 工具调用。原因见 [Owner 通道与上游交接队列物理隔离](ai4-353s.md) 的 2026-10-19 决策修订。

核心对象与状态：TaskSession 按 task_node_id 固定一个受平台生成的 session_id，状态为 active、waiting、cancelled、failed、completed；OwnerCommand 以 idempotency_key 唯一，状态为 accepted、running、succeeded、failed、cancelled；ExecutionRecord 每次实际 Worker 尝试一条不可变记录，状态为 created、running、waiting、succeeded、failed、cancelled；AuditEvent 追加记录命令接收、状态迁移、Worker 创建/退出、运行时结果和错误摘要。重复 idempotency_key 返回原命令和执行结果，不创建第二次执行。

执行边界：Gateway 核验命令后在一次 SQLite 事务中写入 OwnerCommand、ExecutionRecord 初始记录和 AuditEvent，再由本地调度器按 task_node_id 串行启动短生命周期 Worker。Worker 通过 Runtime Adapter 调用已配置的 `fast-agent-mcp` Harness/Worker 入口，使用固定 session_id、专属持久 home、connection scope 和 session history；Gateway 保存 task/session/execution 映射并负责跨请求恢复。首版默认关闭自动 compaction；Worker 返回后写入结果、最终状态和 AuditEvent，然后释放进程。

适配器接口：Gateway 核心只依赖 Runtime Adapter（run/resume/cancel）、Execution Store（读写上述对象）和 Worker Scheduler（排队、串行、取消）；首版使用 SQLite Store、本地进程 Scheduler 和 fast-agent subprocess/Harness Adapter。EventBus、Redpanda、领域 MCP、上游交接队列和 A2A Human Input 不进入 MVP。

失败与恢复：运行时异常、超时、非零退出和无法恢复的 session 均将当前 ExecutionRecord 标记为 failed，并保留错误摘要；平台恢复后只恢复未完成的持久化命令/执行读取，不自动重做已失败执行。取消请求优先写入并审计，调度器尽力终止 Worker；已完成执行不可取消。同一 task_node_id 不允许并发 Worker，恢复必须复用相同 session_id，新的重试由新的 ExecutionRecord 表示。

验证边界：使用标准库单元/集成测试从 HTTP 公共 seam 验证命令幂等、状态查询、取消、失败记录、Worker 释放和 session 恢复；使用已验证的 passthrough fast-agent 作为最小运行时集成测试，不调用真实模型凭据。该决策完成后进入 `/to-spec`，再拆实现 tickets；本票不直接编写产品代码。
