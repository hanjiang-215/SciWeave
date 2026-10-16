# 动态科研协作平台

本术语表定义 AI4Sci 动态科研协作平台的核心领域词汇，统一 Wayfinder 需求地图、产品规格和后续实现中的概念边界。

## 研究图与任务

**Research Mapping（研究 Mapping）**：一个科研项目唯一的、完整的研究任务关系图，包含 TaskNode 和它们之间的依赖边；展示视图只是对它的筛选和投影，不是独立事实源。

**TaskNode（任务节点）**：Research Mapping 中的唯一拓扑节点，表示一个需要规划、执行、讨论、审核或推进的科研任务；平台不预设固定的学科任务类型。

**Dependency Edge（依赖边）**：连接两个 TaskNode 的关系，保存信息依赖、执行阻塞、所需输出和激活条件；节点不重复保存前置或后继节点列表。

**Mapping View（Mapping 视图）**：从 Research Mapping 筛选或投影出的展示结果，例如路线、任务、负责人、Agent、资源引用或历史视图；视图不拥有独立事实。

## 协作与治理

**Proposal（变更提案）**：对正式 Research Mapping 或其受治理内容提出的结构化变更请求，例如新增任务、修改依赖、废弃路线或申请回滚。

**MCP Submission（MCP 提交）**：端侧 Agent 通过标准化 MCP 工具提交任务结果、失败报告或 Proposal 的行为；它是平台接收 Agent 变更的统一入口，不等于正式批准。

**Central Agent（中央 Agent）**：负责调度、注册信息维护以及 Proposal 的格式、依赖、权限和影响范围预审的 Agent；它不替代研究负责人进行科研内容判断和最终批准。

**Personal Agent（Personal Agent）**：研究人员使用自己的 harness 配置的 Agent，通过 MCP、Skills、系统提示词和 Hooks 接入科研协作平台。

**Task Agent（任务 Agent）**：平台支持的轻量化、可配置 Agent，用于执行边界明确、重复、耗时或结构化的科研任务；它不是平台自研的通用 harness。

## 版本与存储

**Mapping Revision（Mapping 版本）**：正式 Research Mapping 在版本化存储中的一次批准状态；第一阶段优先以 TerminusDB 的正式 Commit 验证这一概念，不预先复制一套独立版本协议。

**Formal Mapping（正式 Mapping）**：项目当前正式分支上最后一个经负责人批准的 Mapping 状态；端侧 Agent 的草稿或候选分支不属于正式 Mapping。

**TerminusDB Commit（TerminusDB 提交）**：TerminusDB 中记录一次图状态变化的存储版本；在本项目中，只有经过平台治理和负责人批准的 Commit 才能成为正式 Mapping 的版本依据。

**Trace（执行痕迹）**：对提交、执行、失败、审核、批准和路线变化等过程事件的记录；它解释 Mapping 如何变成当前状态，但不替代 Mapping 本身。

**Mapping Status（Mapping 状态）**：TaskNode 或 Dependency Edge 在治理流程中的生命周期状态，例如 `draft`、`approved`、`rejected`、`superseded` 和 `invalidated`；状态决定对象能否出现在正式视图或参与正式调度。

**Formal Mapping View（正式 Mapping 视图）**：只展示已批准且有效的 TaskNode 和 Dependency Edge 的查询视图，用于正式进度、依赖判断和任务调度；它不是独立物理图。

**Draft Mapping View（草稿 Mapping 视图）**：展示某个 Proposal 变更应用后的预览结果，可包含尚未批准的节点和边；草稿视图不能触发正式调度或发布正式资源。

**Proposal Preview（提案预览）**：将 Proposal 的结构化变更应用到当前正式 Mapping 后生成的临时视图，用于负责人查看结构 Diff 和影响分析。

**ChangeSet（变更集）**：Proposal 中描述新增、修改、废弃或恢复节点和边的结构化操作集合；它是生成草稿预览和正式提交的机器可读依据。
