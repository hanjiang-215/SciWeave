---
id: ai4-yyy9
status: open
deps: []
links: [ai4-xup8, ai4-ufqu, ai4-v19u, ai4-353s, ai4-z3z4]
created: 2026-10-19T06:46:37Z
type: epic
priority: 1
assignee: Frank Qi
tags: [wayfinder:map]
---
# Gateway 与最小 fast-agent 执行闭环规格地图

为 SciWeave 规划一个可交给实现的最小 Gateway 与 `fast-agent-mcp` 执行闭环。Agent Kit 扩展、领域 MCP 接入和 ZIP 交付不属于本阶段。该地图承接既有端侧 Agent 运行时决策，先收敛最小实现前置边界，再交给规格和代码实现阶段。

## Design

## Destination
形成可交给代码实现的最小 Gateway 与 `fast-agent-mcp` 规格：Gateway 能接收一个受控 Owner 请求，管理 Task Session、Execution Record 和 AuditEvent，按需启动短生命周期 Worker，通过运行时适配层完成一次 Agent loop，并支持查询、失败、取消和固定会话恢复。

## Notes
承接既有端侧 Agent 规格；优先跑通最小闭环，暂不接入 Research Mapping、领域 MCP、Redpanda 上游交接队列、Agent Kit manifest 或 ZIP 部署。已有 fast-agent-mcp、TaskNode 模板、Gateway/A2A、Worker 生命周期和审计边界作为输入。外部运行时通过适配器接入，Gateway 核心不复制领域治理逻辑。

## Decisions so far

- [Gateway MVP 状态模型与端口边界](ai4-gq0k.md)：首版采用 Python 标准库 HTTP、SQLite、本地进程调度和 fast-agent Runtime Adapter；固定 session_id、持久 home、connection scope、session history，默认关闭 compaction；不接入 EventBus、Redpanda、领域 MCP 或 A2A Human Input。技术规格见 [Gateway MVP 与最小 fast-agent 技术规格](ai4-z3z4.md)。

## Not yet specified

本阶段没有阻塞实现规格的未决问题；实现拆分和代码任务由 [Gateway MVP 与最小 fast-agent 技术规格](ai4-z3z4.md) 进入下一阶段。

## Out of scope
- [Agent Kit manifest 与模板覆盖规则](ai4-jfvy.md)：本阶段不实现 Agent Kit、Skills/Hooks 模板和多套件定制；待最小闭环稳定后另立阶段。
- [Research Mapping MCP 依赖图最小适配边界](ai4-wglb.md)：本阶段不接入 Research Mapping 或其他领域 MCP；待 Gateway 闭环稳定后另立阶段。
- [Agent Kit ZIP 交付与跨服务器验证边界](ai4-rowi.md)：本阶段不实现 ZIP 交付、跨服务器安装和生产部署；待后续交付阶段另立地图。
- Redpanda 上游交接队列、完整 A2A Human Input 桥接、完整 Research Mapping 领域治理、首版完整 Agent 市场、复杂多租户权限、跨 Mapping/Wiki 原子写入和生产级自动恢复。


**2026-10-19T06:58:30Z**

2026-10-19：目标收敛为最小 Gateway + fast-agent-mcp 执行闭环。MCP 依赖图、Agent Kit manifest 和 ZIP 交付明确移出本地图，后续另立阶段。当前唯一前沿为 Gateway MVP 状态模型与端口边界。

**2026-10-19T07:06:23Z**

2026-10-19 前沿推进：Gateway MVP 状态模型与端口边界已完成决策。首版采用 Python 标准库 HTTP + sqlite3、本地进程调度和 fast-agent Runtime Adapter；固定 session_id、专属持久 home、connection scope、session history，默认关闭 compaction；不接 EventBus、Redpanda、领域 MCP、A2A Human Input 或真实模型。地图已达到 `/to-spec` 交接条件。
