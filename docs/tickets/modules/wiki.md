# 工单模块：LLM-Wiki

> 由 `ticket-index` 技能生成，请勿手工编辑。总览：[索引](../INDEX.md) · 归属与简介：[index.toml](../index.toml)

**范围**：Wiki 内容与资源引用、Buffer/Proposal 生命周期、候选治理记录、分支能力验证

**统计**：共 12 张 · 活跃 5（open 5 / in_progress 0） · 已关闭 7 · 地图 1

## 工单层级

- [ai4-orpg](../../../.tickets/ai4-orpg.md) **LLM-Wiki 持久化与正式化实现地图** — 组织 Wiki 规格前置、正式查询、候选提交审阅及跨存储恢复实现 `epic` `map` `P1` `open` `hanjiang` · 上级 [ai4-xup8](../../../.tickets/ai4-xup8.md)（Research Mapping）
  - [ai4-91tk](../../../.tickets/ai4-91tk.md) **Wiki 正式内容与资源引用查询纵向实现** — 实现正式 WikiRevision 查询及精确版本资源引用解析与异常隔离 `feature` `P1` `open` `hanjiang` · 阻塞于 [ai4-vczt](../../../.tickets/ai4-vczt.md)（open）
  - [ai4-jdjx](../../../.tickets/ai4-jdjx.md) **Wiki 候选审阅、正式化与恢复纵向实现** — 实现 Wiki 候选冲突审阅、Owner 决策、正式化及失败恢复 `feature` `P1` `open` `hanjiang` · 阻塞于 [ai4-txhf](../../../.tickets/ai4-txhf.md)（open）、[ai4-vczt](../../../.tickets/ai4-vczt.md)（open）
  - [ai4-txhf](../../../.tickets/ai4-txhf.md) **Wiki 文档提交与候选 Proposal 纵向实现** — 实现 Wiki 单文档及完整资源引用接纳、候选版本与 Proposal 提交 `feature` `P1` `open` `hanjiang` · 阻塞于 [ai4-91tk](../../../.tickets/ai4-91tk.md)（open）、[ai4-vczt](../../../.tickets/ai4-vczt.md)（open）
  - [ai4-vczt](../../../.tickets/ai4-vczt.md) **Wiki ResourceVersion 资格审核与撤回纵向实现** — 实现资源版本授权审核、资格状态与撤回审计，供 Wiki 候选和正式化校验使用 `feature` `P1` `open` `hanjiang`
  - [ai4-7xtf](../../../.tickets/ai4-7xtf.md) **Wiki 资源审核与跨存储正式化前置规格** — 明确 ResourceVersion 正式引用审核依据及 Wiki 跨存储正式化和恢复规则 `task` `P1` `closed` `hanjiang`
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
