---
id: ai4-yyy9
status: open
deps: []
links: [ai4-xup8, ai4-ufqu, ai4-v19u, ai4-353s, ai4-z3z4, ai4-yvh2]
created: 2026-10-19T06:46:37Z
type: epic
priority: 1
assignee: hanjiang
tags: [wayfinder:map]
---
# Gateway 与最小 fast-agent 执行闭环规格地图

为 SciWeave 规划一个可交给实现的最小 Gateway 与 `fast-agent-mcp` 执行闭环。Agent Kit 扩展、领域 MCP 接入和 ZIP 交付不属于本阶段。该地图承接既有端侧 Agent 运行时决策，先收敛最小实现前置边界，再交给规格和代码实现阶段。

## Design

## Destination
形成可交给代码实现的最小 Gateway 与 `fast-agent-mcp` 规格：Gateway 能接收一个人工请求，管理 Task Session、Execution Record 和 AuditEvent，按需启动短生命周期 Worker，通过运行时适配层完成一次 Agent loop，并支持查询、失败、取消和固定会话恢复。

> 修订（2026-10-21）：「受控 Owner 请求」改为「人工请求」，因为任务下发已改走消息队列，Gateway 的 MCP 只承担返修与处置。Worker 由 Gateway 启动这一核心不变；Gateway 所在位置不再限定为中央服务器——task-agent 的 Gateway 部署在任务负责人处，「服务端」在本文档中泛指 Gateway 所在的进程侧。依据「Agent 以消息驱动，Gateway 的 MCP 只负责返修」与「Task Agent 改由研究员端侧自持」。

## Notes

**2026-10-25 转交（hanjiang）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。转交原因：Frank Qi 暂时无法继续推进项目，经其本人授权，由 hanjiang 接手本票后续推进与收口。原负责人 Frank Qi，转交时间 2026-10-25T12:41:00Z。转交只变更归属并记录，不改写正文、验收标准与既有决策。

承接既有端侧 Agent 规格；优先跑通最小闭环，暂不接入 Research Mapping、领域 MCP、Redpanda 上游交接队列、Agent Kit manifest 或 ZIP 部署。已有 fast-agent-mcp、TaskNode 模板、Owner 通道、Worker 生命周期和审计边界作为输入。外部运行时通过适配器接入，Gateway 核心不复制领域治理逻辑。

## Decisions so far

- [Gateway MVP 状态模型与端口边界](ai4-gq0k.md)：首版采用 MCP（Streamable HTTP）作为 Owner 入口、SQLite 持久化、本地进程调度和 fast-agent Runtime Adapter；固定 session_id、持久 home、connection scope、session history，默认关闭 compaction；不接入 EventBus、Redpanda、领域 MCP 或 A2A Human Input。技术规格见 [Gateway MVP 与最小 fast-agent 技术规格](ai4-z3z4.md)。
- [Owner 通道与上游交接队列物理隔离](ai4-353s.md)：Owner 的 Codex 通过 MCP 调用常驻 Gateway；上游 TaskNode 交接通过消息队列和上游收集器。A2A 不用于 Owner 通道，因为主流 harness 均未内置 A2A 客户端。

  > 修订（2026-10-21）：Owner 通道的用途收窄为返修与处置，任务下发改走消息队列；Gateway 位置由中央改为任务负责人处。见「Agent 以消息驱动，Gateway 的 MCP 只负责返修」与「Task Agent 改由研究员端侧自持」。

  > 再修订（2026-10-22）：「Agent 以消息驱动，Gateway 的 MCP 只负责返修」收口。`submit_owner_command` 删除，不保留为返修入口。物理隔离仍然成立。
- [执行与接纳状态机融合及 Owner 审核工具边界](ai4-yvh2.md)：Gateway 归入 `sci-weave/task-agent` 项目组；同一 TaskNode 串行、跨 TaskNode 可并发。MCP 与上游交接汇入 Gateway，使用 `blocked`、`queued`、`running`、`waiting`、`awaiting_acceptance` 等状态及 `review_execution` 完成可审计审核；接纳不自动创建领域草稿。

  > 修订（2026-10-21）：状态机、串行化与审核工具边界仍然成立；「MCP 与上游交接汇入 Gateway」改为「上游交接经消息队列汇入，MCP 只承担返修与处置」。

  > 再修订（2026-10-22）：`blocked`、`awaiting_acceptance`、`accepted` 和 `owner_command` 删除。正常终点是 `completed` 并保存 `draft_id`；`review_execution` 没有 `accept`。现行状态机见「最小 Work Agent 实现规格」。
- [Task Agent 项目组三角色部署与双入口调度边界](ai4-6fb7.md)：`mcp`、`ingest` 与短生命周期 `worker` 构成 Task Agent 项目组；两种入口通过共享 SQLite 持久化包、原子执行租约和稳定排序串行调度，健康按组件实际可用性聚合。Mapping 初始化查询另由受阻塞子票收敛。

  > 修订（2026-10-21）：三角色构成、共享 SQLite、原子租约与稳定排序都仍然成立；变化的是部署位置——整个项目组由中央移到任务负责人处，`ingest` 变成端侧主动连接中央队列的订阅器。
- [Gateway MCP 对外协议版本、鉴权与错误契约](ai4-zfz9.md)：最小 MCP v1 使用本地 Bearer 令牌与配置 Caller，区分 HTTP/JSON-RPC 与工具业务错误；OwnerCommand 仅留痕，ExecutionRecord 是唯一工作流状态机，领域 Buffer 保持开放且不自动创建。

## Not yet specified

并行接入领域治理时的执行记录归属：本阶段 Gateway 只服务端侧闭环，Execution Record 与 Mapping 治理 SQLite 的关系留待接入 Research Mapping 后决定。

MVP 的调用者身份与 TaskNode Owner 授权绑定：当前只有本地开发令牌，尚未定义多人身份和每个 TaskNode 的 Owner 授权校验。

## Out of scope
- [Agent Kit manifest 与模板覆盖规则](ai4-jfvy.md)：本阶段不实现 Agent Kit、Skills/Hooks 模板和多套件定制；待最小闭环稳定后另立阶段。
- [Research Mapping MCP 依赖图最小适配边界](ai4-wglb.md)：本阶段不接入 Research Mapping 或其他领域 MCP；待 Gateway 闭环稳定后另立阶段。
- [Agent Kit ZIP 交付与跨服务器验证边界](ai4-rowi.md)：本阶段不实现 ZIP 交付、跨服务器安装和生产部署；待后续交付阶段另立地图。
- Redpanda 上游交接队列、A2A 传输、完整 Research Mapping 领域治理、首版完整 Agent 市场、复杂多租户权限、跨 Mapping/Wiki 原子写入和生产级自动恢复。


**2026-10-19T06:58:30Z**

2026-10-19：目标收敛为最小 Gateway + fast-agent-mcp 执行闭环。MCP 依赖图、Agent Kit manifest 和 ZIP 交付明确移出本地图，后续另立阶段。当前唯一前沿为 Gateway MVP 状态模型与端口边界。

**2026-10-19T07:06:23Z**

2026-10-19 前沿推进：Gateway MVP 状态模型与端口边界已完成决策。首版采用 Python 标准库 HTTP + sqlite3、本地进程调度和 fast-agent Runtime Adapter；固定 session_id、专属持久 home、connection scope、session history，默认关闭 compaction；不接 EventBus、Redpanda、领域 MCP、A2A Human Input 或真实模型。地图已达到 `/to-spec` 交接条件。

**2026-10-19T08:53:34Z**

关联 Gitee Pull Request #9：https://gitee.com/qi-yueran/ai4science/pulls/9（目标 develop）。Gateway MVP 地图、决策票、技术规格和实现任务已进入 PR。

**2026-10-19T20:14:00Z**

地图修订（2026-10-19）：Owner 通道由 A2A 改为 MCP（Streamable HTTP）。事实依据：Codex CLI、Cursor、Claude Code 对外扩展面只有 MCP，均未内置 A2A 客户端；A2A 面向 Agent 间协作，harness 是 Agent 宿主，协议定位不匹配。修订后 Owner 侧由 Codex 在 `mcp_servers` 注册 Gateway 地址与令牌，Gateway 暴露 `submit_owner_command`、`query_execution`、`cancel_execution`、`list_pending`、`health` 五个工具。上游队列路径不变。A2A 不再出现在本地图的 Owner 链路中。

**2026-10-22T13:16:53Z**

2026-10-22：不新开规格。放置结论写入「最小 Work Agent 实现规格」的「源码放置」与 ADR-0002。Centre Agent 在 centre-agents，研究员套件在 deploy-task-agent，两份源码不对 path 依赖。sci-weave/task-agent 只作 git mv 起点。
