# 工单模块：Agent 与消息协作

> 由 `ticket-index` 技能生成，请勿手工编辑。总览：[索引](../INDEX.md) · 归属与简介：[index.toml](../index.toml)

**范围**：端侧 Agent 角色、消息与交接、套件接入、Task Agent 部署与运行时验证

**统计**：共 11 张 · 活跃 7（open 6 / in_progress 1） · 已关闭 4 · 地图 0

## 工单层级

- [ai4-6fb7](../../../.tickets/ai4-6fb7.md) **Task Agent 项目组三角色部署与双入口调度边界** — 确定 Task Agent 项目组的目录、三个角色、共享 SQLite、双入口启动与上游优先规则 `task` `P1` `open` `Frank Qi` · 上级 [ai4-yyy9](../../../.tickets/ai4-yyy9.md)（Gateway 与执行运行时）
- [ai4-kpvp](../../../.tickets/ai4-kpvp.md) **端侧 Agent 协作与治理分支** — 界定 Personal Agent、Task Agent 与平台在任务执行、提交和审核治理中的协作边界 `epic` `P1` `open` `Frank Qi` · 上级 [ai4-xup8](../../../.tickets/ai4-xup8.md)（Research Mapping）
  - [ai4-ufqu](../../../.tickets/ai4-ufqu.md) **Task Agent 运行时与套件接入方案** — 确定首版 Task Agent 运行时形态、MCP/Skills/Hooks 接入方式与平台职责边界 `epic` `P1` `in_progress` `Frank Qi`
    - [ai4-a9zd](../../../.tickets/ai4-a9zd.md) **验证 fast-agent-mcp 外部进程与 A2A 启动路径** — 验证外部子进程和 A2A 两条 fast-agent-mcp 最小启动路径 `task` `P1` `open` `Frank Qi`
    - [ai4-glmy](../../../.tickets/ai4-glmy.md) **fast-agent-mcp 历史保存、恢复与上下文隔离验证** — 验证 fast-agent-mcp 的历史保存、恢复、窗口、压缩与会话隔离行为 `task` `P1` `closed` `Frank Qi`
  - [ai4-csyj](../../../.tickets/ai4-csyj.md) **TaskNode 交接消息发布与下游触发流程** — 定义审核通过后沿依赖边发布交接消息的触发、载荷、投递重试与下游激活语义 `epic` `P1` `open` `Frank Qi`
  - [ai4-wd5l](../../../.tickets/ai4-wd5l.md) **Task Agent 与审核人协作及返修流程** — 定义 Task Agent 与审核人之间的结果提交、澄清、返修、驳回和人工接管流程 `epic` `P1` `closed` `Frank Qi`
- [ai4-te1v](../../../.tickets/ai4-te1v.md) **消息队列协作模型分支** — 界定多人多 Agent 协作的消息模型、交接语义和触发规则，不选具体队列产品 `epic` `P1` `open` `Frank Qi` · 上级 [ai4-xup8](../../../.tickets/ai4-xup8.md)（Research Mapping）
- [ai4-v19u](../../../.tickets/ai4-v19u.md) **Agent 套件接入与协作边界分支** — 界定 Agent 套件中 MCP、Skills、Hooks 的职责、接入方式和协作边界 `epic` `P1` `open` `未分配` · 上级 [ai4-xup8](../../../.tickets/ai4-xup8.md)（Research Mapping）
- [ai4-jfvy](../../../.tickets/ai4-jfvy.md) **Agent Kit manifest 与模板覆盖规则** — 定义 Agent Kit manifest 的字段与模板覆盖规则，作为套件交付的实现前置 `epic` `P1` `closed` `Frank Qi` · 上级 [ai4-yyy9](../../../.tickets/ai4-yyy9.md)（Gateway 与执行运行时）
- [ai4-rowi](../../../.tickets/ai4-rowi.md) **Agent Kit ZIP 交付与跨服务器验证边界** — 界定 Agent Kit ZIP 交付与跨服务器验证的范围（当前地图外，待后续阶段） `epic` `P1` `closed` `Frank Qi` · 上级 [ai4-yyy9](../../../.tickets/ai4-yyy9.md)（Gateway 与执行运行时）

## 跨模块归属

以下工单主模块在其他领域，同时归属本模块：

- [ai4-353s](../../../.tickets/ai4-353s.md) **Task Owner 通道（MCP）与上游交接队列物理隔离** — 确定 Owner MCP、上游交接队列、常驻 Gateway 与短生命周期 Worker 的物理隔离（主模块：[Gateway 与执行运行时](gateway.md)）
- [ai4-m0vt](../../../.tickets/ai4-m0vt.md) **首版任务执行、交接与失败恢复模型** — 定义首版 Execution Record、结果提交、负责人接纳、重试、转交、接管与路线变更触发规则（主模块：[Research Mapping](mapping.md)）
- [ai4-xup8](../../../.tickets/ai4-xup8.md) **Research Mapping 与 Wiki 领域数据模型和持久化规格地图** — 收敛 Mapping/Wiki 数据模型与持久化规则，并厘清消息、套件和端侧 Agent 边界（主模块：[Research Mapping](mapping.md)）
- [ai4-yyy9](../../../.tickets/ai4-yyy9.md) **Gateway 与最小 fast-agent 执行闭环规格地图** — 规划最小 Gateway 与 fast-agent 执行闭环，收敛 Owner 请求、会话、执行、审计和运行时边界（主模块：[Gateway 与执行运行时](gateway.md)）
