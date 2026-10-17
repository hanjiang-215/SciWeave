# 动态科研协作平台

本术语表定义 AI4Sci 动态科研协作平台的核心领域词汇，统一 Wayfinder 需求地图、产品规格和后续实现中的概念边界。

## 研究图与任务

**Research Mapping（研究 Mapping）**：一个科研项目唯一的、完整的研究任务关系图，包含 TaskNode 和它们之间的依赖边；展示视图只是对它的筛选和投影，不是独立事实源。

**Research Mapping Store（研究 Mapping 存储）**：独立处理 Research Mapping 的 TerminusDB 实例或逻辑存储边界，保存 TaskNode、Dependency Edge、MappingRevision 及其候选分支和正式视图。它不保存 WikiDocument、WikiRevision 或资源本体。

**LLM-Wiki Store（LLM-Wiki 存储）**：独立处理 LLM-Wiki 的 TerminusDB 实例或逻辑存储边界，保存 WikiDocument、WikiRevision、Resource、ResourceVersion、RawArtifact 元数据及其引用关系。它不保存 TaskNode 或 Dependency Edge。

**Domain Isolation（领域隔离）**：Research Mapping 与 LLM-Wiki 在第一阶段采用独立的领域运行边界，分别拥有自己的管理 MCP、Buffer、内存数据边界、校验器、TerminusDB、candidate branch、Revision 和审计链。一个 Central Agent 可以通过两个独立的管理 MCP 分别处理两个领域，但不得共享领域对象、数据库连接、Buffer 或跨域写入状态；两个领域只能通过稳定的对象 ID 和版本 ID 建立显式弱引用，第一阶段不支持单个 MCP Submission 或 Proposal 同时修改两个领域。

**TaskNode（任务节点）**：Research Mapping 中的唯一拓扑节点，表示一个需要规划、执行、讨论、审核或推进的科研任务；平台不预设固定的学科任务类型。

**Dependency Edge（依赖边）**：连接两个 TaskNode 的关系，保存信息依赖、执行阻塞、所需输出和激活条件；节点不重复保存前置或后继节点列表。

**Mapping View（Mapping 视图）**：从 Research Mapping 筛选或投影出的展示结果，例如路线、任务、负责人、Agent、资源引用或历史视图；视图不拥有独立事实。

**WikiDocument（Wiki 文档）**：LLM-Wiki 中一个具有稳定逻辑身份的文档对象，例如来源文档、实体、概念或综合内容。WikiDocument 的正文通过多个 WikiRevision 版本保存；更新文档不会覆盖已有正式版本。只有当前 Formal WikiRevision 才能作为正式查询结果。

**WikiRevision（Wiki 文档版本）**：WikiDocument 的一次不可变内容版本，包含 Markdown 正文、页面元数据、来源引用、创建者、创建时间、基础版本、Proposal 关联和治理状态。草稿版本可以在 Proposal 预览中查看，但正式 MCP 查询只返回最新 Formal WikiRevision。

**Formal WikiRevision（正式 Wiki 版本）**：已经通过 Proposal 整体审核并被平台正式查询指针选中的 WikiRevision。TerminusDB Commit 只记录存储变化，不能单独证明 WikiRevision 已经正式批准。

**Wiki Metadata（Wiki 页面元数据）**：随 WikiRevision 展示的页面描述信息，例如文档类型、标题、文档标识、版本标识、状态和时间。Metadata 可以出现在 Markdown frontmatter 中，但 Proposal 状态、正式版本指针、资源版本关系、审计记录和访问权限等治理事实以 TerminusDB 的结构化记录为准。

**Formal Query（正式查询）**：只读取当前 Formal WikiRevision、正式 Resource Reference 和正式资源版本的查询能力。正式查询不读取草稿或 candidate branch 当前状态。

**Proposal Preview（提案预览）**：在明确 Proposal 上下文中读取 candidate branch 草稿、生成 Diff 和查看影响范围的能力。提案预览与正式查询分离，预览内容带有草稿标记，不能直接参与正式调度或形成正式研究结论。

**Candidate Commit（候选提交）**：由 Formal WikiRevision 派生、写入 candidate branch 的不可变存储版本。Candidate Commit 只表示候选内容和存储历史，不表示已经正式批准；提交 Merge Request Buffer 后，关联的 candidate head 被锁定为本次正式化审核对象。

**Merge Request Buffer（合并请求缓冲）**：Agent 通过 Wiki MCP 提交的正式化请求，引用一个或多个 candidate Commit、固定 candidate head、基准 Formal WikiRevision、diff/merge dry-run 结果和候选解决方案。Project Owner 从完整方案中只能选择一个批准或驳回；方案可以是直接采用一个候选，也可以是 `blended` 的新候选结果；它不重复承载 Wiki 正文。

**Candidate Resolution（候选解决版本）**：Agent 针对多个冲突 candidate branch 生成的新候选版本。它可以选择某个候选、综合多个候选或放弃部分修改，但不能改写其他提交者的原始 candidate branch 或 Commit。综合多个来源形成的新候选结果称为 `blended`，必须拥有自己的不可变 candidate Commit。

**Draft Acceptance Review（草稿接纳审核）**：端侧 Agent 提交修改后进行的第一阶段审核。Research Mapping 变更由相关 TaskNode 负责人审核；LLM-Wiki 变更由 Wiki Curator、Resource Owner 或文档负责人审核。审核通过后，Buffer 中的变更才可以分别写入对应的 TerminusDB candidate branch，形成 WikiRevision 或 Mapping Revision 草稿；该审核不代表内容已经成为正式科研事实。

**Formal Publication Review（正式发布审核）**：草稿转为正式版本前，由项目负责人进行的第二阶段审核。只有审核通过并更新 Formal WikiRevision 或 Formal Mapping Revision 指针后，内容才能进入正式查询和正式调度。

**Task Node Owner（任务节点负责人）**：对相关 TaskNode 的任务修改、结果和证据进行第一阶段审核的责任人。其审核范围是草稿接纳，不替代项目负责人进行正式发布批准。

**Project Owner（项目负责人）**：对项目正式 Research Mapping、Wiki 内容及其治理变更承担最终审核责任的人，负责草稿转正式版本的正式发布审核。

**LLM-Wiki（大语言模型科研 Wiki）**：面向科研项目的文字知识与证据索引空间。LLM-Wiki 保存研究说明、结构化元数据和对外部科研资源的引用，不保存数据、代码、实验文件等资源本体；其内容可以由人或 Agent 提交，并经过项目治理流程形成正式版本。平台仅参考 Harness Wiki 的 LLM-Wiki 文档分类和治理方式，不将 Harness Wiki 作为本平台的整体存储架构或唯一事实源。

**Resource Reference（资源引用）**：LLM-Wiki 中指向外部科研资源的一条结构化记录，而不是资源本体。记录至少包括资源类型、外部定位信息、不可变版本标识（如 DOI、提交号或数据集版本）、来源任务、创建者、生成时间、输入资源、治理状态、被引用的 Wiki 文档或研究结论，以及资源可访问性状态。数据、代码、论文、实验结果和图表等资源由外部系统保存，Resource Reference 负责让它们可发现、可解释和可追溯。

**Resource Reference Status（资源引用状态）**：描述外部资源当前可追踪性的状态，例如 `available`、`unavailable`、`moved`、`superseded` 和 `archived`；资源链接失效不会删除历史引用，但正式视图应提示当前不可用。

## 协作与治理

**Proposal（变更提案）**：对正式 Research Mapping 或 LLM-Wiki 受治理内容提出的结构化变更请求。Mapping Proposal 只修改 Research Mapping；Wiki Proposal 只修改 LLM-Wiki；第一阶段不存在跨域 Proposal。

**Wiki Proposal（Wiki 变更提案）**：由一个或多个已通过第一阶段接纳审核的 Wiki Buffer Submission 组成的 Wiki 治理单元。Wiki Proposal 关联 candidate branch、candidate Commit、Merge Request Buffer、基准 Formal WikiRevision 和正式化结果；它可以包含多个文档变更，但默认整体选择和整体正式化。

**MCP Submission（MCP 提交）**：端侧 Agent 通过标准化 MCP 工具提交任务结果、失败报告或 Proposal 的行为；它是平台接收 Agent 变更的统一入口，不等于正式批准。

**Central Agent（中央 Agent）**：负责调度、注册信息维护以及 Proposal 的格式、依赖、权限和影响范围预审的 Agent；它不替代研究负责人进行科研内容判断和最终批准。

**Personal Agent（Personal Agent）**：研究人员使用自己的 harness 配置的 Agent，通过 MCP、Skills、系统提示词和 Hooks 接入科研协作平台。

**Task Agent（任务 Agent）**：平台支持的轻量化、可配置 Agent，用于执行边界明确、重复、耗时或结构化的科研任务；它不是平台自研的通用 harness。

## 版本与存储

**Mapping Revision（Mapping 版本）**：Research Mapping 在版本化存储中的一个具体版本。FormalRevision 是已经通过负责人审核、可供正式查询的版本；TerminusDB Commit 是其底层存储版本，两者通过平台治理记录关联。

**Formal Mapping（正式 Mapping）**：单一物理 Research Mapping 中由当前最新 FormalRevision 形成的查询投影；草稿节点和草稿边可以共存于同一物理图，但不属于正式投影。

**TerminusDB Commit（TerminusDB 提交）**：TerminusDB 中记录一次图状态变化的存储版本；它可以对应草稿或正式数据，只有经过平台治理和负责人批准并关联到 FormalRevision 的 Commit 才能作为正式 Mapping 的版本依据。

**FormalRevision（正式版本）**：经负责人批准、可被普通查询读取的 Mapping 版本标识；它关联对应的 TerminusDB Commit、来源 Proposal 和审核结果。

**Trace（执行痕迹）**：对提交、执行、失败、审核、批准和路线变化等过程事件的记录；它解释 Mapping 如何变成当前状态，但不替代 Mapping 本身。

**Mapping Status（Mapping 状态）**：TaskNode 或 Dependency Edge 在治理流程中的生命周期状态，例如 `draft`、`approved`、`rejected`、`superseded` 和 `invalidated`；状态决定对象能否出现在正式视图或参与正式调度。

**Formal Mapping View（正式 Mapping 视图）**：只展示已批准且有效的 TaskNode 和 Dependency Edge 的查询视图，用于正式进度、依赖判断和任务调度；它不是独立物理图。

**Draft Mapping View（草稿 Mapping 视图）**：展示某个 Proposal 变更应用后的预览结果，可包含尚未批准的节点和边；草稿视图不能触发正式调度或发布正式资源。

**Proposal Preview（提案预览）**：将 Proposal 的结构化变更应用到当前正式 Mapping 后生成的临时视图，用于负责人查看结构 Diff 和影响分析。

**ChangeSet（变更集）**：Proposal 中描述新增、修改、废弃或恢复节点和边的结构化操作集合；它是生成草稿预览和正式提交的机器可读依据。
