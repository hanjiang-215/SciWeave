# 任务下发只走消息队列，MCP 只承担处置与观察

Work Agent（Task Agent 与 Centre Agent）的任务下发统一经消息队列，不经 MCP。MCP 层面只保留人要做的事：返修、放弃、转人工、回答提问、观察与取消。

## Status

accepted（2026-10-22）

## Considered Options

1. **MCP 直连下发**（原设计）：Project Owner 的 harness 调 `submit_owner_command` 触发首次执行，上游交接也经消息入口进同一个 Gateway。否决理由：它要求人的 harness 一直连着 Gateway，而任务下发本质上是异步事件；它还把「下发任务」和「人工介入」混进同一张工具表，两者的授权、幂等与审计要求不同。
2. **A2A 传输**：一度用于 Owner 通道。否决理由：主流 harness（Codex CLI、Cursor、Claude Code）对外扩展面只有 MCP，均未内置 A2A 客户端；A2A 面向 Agent 间协作，与 harness 作为 Agent 宿主的定位不匹配。
3. **消息队列下发 + MCP 处置**（采纳）：任务下发是异步事件，走队列；人的介入是同步请求，走 MCP。

## Consequences

- 一个 Work Agent 需要三个组件：`gateway/mcp`（处置面）、`gateway/subscriber`（消息监听）、`worker`（一轮 loop）。订阅器必须常驻以持有 consumer group 与 offset，因此不能并进 MCP 进程。
- Gateway 不再有 `submit_owner_command`，也不再需要判断「上游是否就绪」：消息能到达就说明上游正式版本已发布，`blocked` 状态因此删除。
- 根任务的首条消息由 Project Owner 触发，上游交接由领域正式版本发布触发，两者都是队列事件而非 MCP 调用。
- `sci-weave/task-agent` 的现有实现仍保留了 `submit_owner_command`，属未清理的旧形态；端侧改写时删除。

## 相关

- 形态与组件划分：`docs/data-flow/work-agent.md`
- 通道分工的推翻过程：`.tickets/ai4-dhpv.md`
- 端侧归属：`.tickets/ai4-we38.md`
- 消息语义（主题、分区、offset）：`.tickets/ai4-te1v.md`，待定
