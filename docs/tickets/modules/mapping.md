# 工单模块：Research Mapping

> 由 `ticket-index` 技能生成，请勿手工编辑。总览：[索引](../INDEX.md) · 归属与简介：[index.toml](../index.toml)

**范围**：TaskNode/依赖边模型、草稿与正式视图、提案生命周期、TerminusDB 验证与持久化

**统计**：共 11 张 · 活跃 1（open 1 / in_progress 0） · 已关闭 10 · 地图 1

## 工单层级

- [ai4-xup8](../../../.tickets/ai4-xup8.md) **Research Mapping 与 Wiki 领域数据模型和持久化规格地图** — 收敛 Mapping/Wiki 数据模型与持久化规则，并厘清消息、套件和端侧 Agent 边界 `epic` `map` `P1` `open` `hanjiang`
  - [ai4-yl2o](../../../.tickets/ai4-yl2o.md) **Research Mapping 持久化模型分支** — 汇总 Research Mapping 图对象字段与 SQLite 候选治理记录的整体持久化规格 `epic` `P1` `closed` `hanjiang`
    - [ai4-mjku](../../../.tickets/ai4-mjku.md) **Research Mapping 候选治理 SQLite 结构化记录模型** — 定义 Research Mapping 侧候选提交、Proposal 与正式化元数据的 SQLite 记录模型 `task` `P1` `closed` `hanjiang`
    - [ai4-t5zl](../../../.tickets/ai4-t5zl.md) **Research Mapping TaskNode 与 Dependency Edge 持久化字段模型** — 把 TaskNode 与 DependencyEdge 领域字段落成可持久化对象、约束和关系模型 `task` `P1` `closed` `hanjiang`
- [ai4-2alw](../../../.tickets/ai4-2alw.md) **TerminusDB 候选分支与草稿工作区行为验证** — 验证 TerminusDB 候选分支的创建、提交、Diff、合并及无正式 Commit 的草稿隔离能力 `task` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）
- [ai4-9hcj](../../../.tickets/ai4-9hcj.md) **TerminusDB Mapping 版本与 Agent 提交原型验证** — 用原型验证 Agent 提交、结构差异、负责人批准形成正式 Commit 及历史恢复链路 `task` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）
- [ai4-m0vt](../../../.tickets/ai4-m0vt.md) **首版任务执行、交接与失败恢复模型** — 定义首版 Execution Record、结果提交、负责人接纳、重试、转交、接管与路线变更触发规则 `grilling` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）
- [ai4-r3so](../../../.tickets/ai4-r3so.md) **Research Mapping 节点与依赖边字段模型** — 定义 TaskNode 与 DependencyEdge 的字段语义、必填条件、状态约束和对象关系 `grilling` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）
- [ai4-u3rs](../../../.tickets/ai4-u3rs.md) **单一 Mapping 的草稿与正式视图模型** — 让同一张研究图同时承载草稿、预审、审核与正式调度，并区分正式、草稿和提案预览视图 `grilling` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）
- [ai4-wglb](../../../.tickets/ai4-wglb.md) **Research Mapping MCP 依赖图最小适配边界** — 界定 Gateway 阶段 Research Mapping MCP 只读依赖图适配的最小范围（当前地图外） `epic` `P1` `closed` `hanjiang` · 上级 [ai4-yyy9](../../../.tickets/ai4-yyy9.md)（Gateway 与执行运行时）
- [ai4-xrxw](../../../.tickets/ai4-xrxw.md) **首版 Mapping Proposal 生命周期与审计证据模型** — 定义首版 Mapping Proposal 的生命周期、正式化门槛、候选预览与审计证据关联 `grilling` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）

## 跨模块归属

以下工单主模块在其他领域，同时归属本模块：

- [ai4-x3nx](../../../.tickets/ai4-x3nx.md) **Research Mapping 与 Wiki 候选变更并发治理地图** — 确定正式基线前进时，其他候选如何保留、重放、语义分析、审核和处置（主模块：[提案治理与审计](governance.md)）
