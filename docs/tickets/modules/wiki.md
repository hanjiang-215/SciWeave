# 工单模块：LLM-Wiki

> 由 `ticket-index` 技能生成，请勿手工编辑。总览：[索引](../INDEX.md) · 归属与简介：[index.toml](../index.toml)

**范围**：Wiki 内容与资源引用、Buffer/Proposal 生命周期、候选治理记录、分支能力验证

**统计**：共 6 张 · 活跃 0（open 0 / in_progress 0） · 已关闭 6 · 地图 0

## 工单层级

- [ai4-2sdn](../../../.tickets/ai4-2sdn.md) **TerminusDB candidate branch 状态标记与只读归档能力验证** — 验证 TerminusDB 分支能否保存治理状态、设置只读归档，以及平台需自持哪些状态 `research` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）
- [ai4-36ek](../../../.tickets/ai4-36ek.md) **Wiki Buffer 提交单位：单文档、文档加引用还是完整 ChangeSet** — 决定 Wiki Buffer 的最小治理对象：单文档、文档加引用，还是完整 ChangeSet `grilling` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）
- [ai4-56iu](../../../.tickets/ai4-56iu.md) **Wiki 持久化模型分支** — 汇总 Wiki 内容对象与 SQLite 候选治理记录的整体持久化规格 `epic` `P1` `closed` `hanjiang` · 上级 [ai4-xup8](../../../.tickets/ai4-xup8.md)（Research Mapping）
  - [ai4-hkdz](../../../.tickets/ai4-hkdz.md) **Wiki 候选治理 SQLite 结构化记录模型** — 定义 Wiki 侧候选提交、Proposal 与正式化元数据的 SQLite 记录模型 `task` `P1` `closed` `hanjiang`
  - [ai4-l3sj](../../../.tickets/ai4-l3sj.md) **LLM-Wiki 内容模型与资源引用字段设计** — 定义 Wiki 内容对象、页面元数据和 Resource Reference 的字段、关系与约束 `task` `P1` `closed` `hanjiang`
- [ai4-zewm](../../../.tickets/ai4-zewm.md) **Wiki Proposal 与 Merge Request Buffer 生命周期** — 定义 Wiki 候选从 Buffer 接纳、Proposal、候选锁定到正式版本的完整生命周期 `grilling` `P1` `closed` `hanjiang` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）

## 跨模块归属

以下工单主模块在其他领域，同时归属本模块：

- [ai4-x3nx](../../../.tickets/ai4-x3nx.md) **Research Mapping 与 Wiki 候选变更并发治理地图** — 确定正式基线前进时，其他候选如何保留、重放、语义分析、审核和处置（主模块：[提案治理与审计](governance.md)）
- [ai4-xup8](../../../.tickets/ai4-xup8.md) **Research Mapping 与 Wiki 领域数据模型和持久化规格地图** — 收敛 Mapping/Wiki 数据模型与持久化规则，并厘清消息、套件和端侧 Agent 边界（主模块：[Research Mapping](mapping.md)）
