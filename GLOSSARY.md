# 动态科研协作平台

本术语表定义 SciWeave 动态科研协作平台的核心领域词汇，统一 Wayfinder 需求地图、产品规格和后续实现中的概念边界。

## 研究图与任务

**Research Mapping（研究 Mapping）**：一个科研项目唯一的、完整的研究任务关系图，包含 TaskNode 和它们之间的依赖边；展示视图只是对它的筛选和投影，不是独立事实源。

**Research Mapping Store（研究 Mapping 存储）**：独立处理 Research Mapping 的 TerminusDB 实例或逻辑存储边界，保存 TaskNode、Dependency Edge、MappingRevision 及其候选分支和正式视图。它不保存 WikiDocument、WikiRevision 或资源本体。

**LLM-Wiki Store（LLM-Wiki 存储）**：独立处理 LLM-Wiki 的 TerminusDB 实例或逻辑存储边界，保存 WikiDocument、WikiRevision、Resource、ResourceVersion、RawArtifact 元数据及其引用关系。它不保存 TaskNode 或 Dependency Edge。

**Domain Isolation（领域隔离）**：Research Mapping 与 LLM-Wiki 在第一阶段采用独立的领域运行边界，分别拥有自己的管理 MCP、Buffer、内存数据边界、校验器、TerminusDB、candidate branch、Revision 和审计链。一个 Centre Agent 可以通过两个独立的管理 MCP 分别处理两个领域，但不得共享领域对象、数据库连接、Buffer 或跨域写入状态；两个领域只能通过稳定的对象 ID 和版本 ID 建立显式弱引用，第一阶段不支持单个 MCP Submission 或 Proposal 同时修改两个领域。

> 修订（2026-10-21）：隔离粒度从「服务」下调为「内容与事务」。两个领域共用中央草稿箱（Draft Buffer）的同一个数据库，但按命名空间分离 schema、审核人、读写授权和事务，仍不共享领域对象 ID，也不做跨域原子写入。原文保留。

**Draft Buffer（中央草稿箱）**：中央服务器上保存尚未进入任何领域候选分支的原始内容的共享服务，内容为 Research Mapping 路线变更草稿与 LLM-Wiki 文档及引用草稿。它只由人审核：草稿通过后由人调用对应领域管理 MCP 写入候选分支，自己不创建候选、不写领域存储、不发起执行。它与 Merge Request Buffer、Execution Submission 是三样不同的东西，一律不以「Buffer」单独指代。

> 修订（2026-10-21）：删去「Task Agent 声明式设计稿」。Task Agent 改由研究员端侧自持，其定义与代码留在研究员的仓库，不进入中央草稿箱。原文保留于版本历史。

**Draft Submission（草稿提交）**：草稿箱中一份被固定为审核对象的草稿版本，以提交时记录的确切存储 Commit 标识。草稿正文在提交后仍可继续修改，但本轮审核结论只针对被固定的那个版本。

**Namespace（命名空间）**：草稿箱内区分内容域与审核规则的字段，取值为 `mapping` 或 `wiki`。审核人配置挂在命名空间上，不挂在每份草稿上；草稿只引用命名空间。

> 修订（2026-10-21）：删去 `task_agent_design`，理由见 Draft Buffer 的修订。

**TaskNode（任务节点）**：Research Mapping 中的唯一拓扑节点，表示一个需要规划、执行、讨论、审核或推进的科研任务；平台不预设固定的学科任务类型。

**Dependency Edge（依赖边）**：连接两个 TaskNode 的关系，保存信息依赖、执行阻塞、所需输出和激活条件；节点不重复保存前置或后继节点列表。

**Mapping View（Mapping 视图）**：从 Research Mapping 筛选或投影出的展示结果，例如路线、任务、负责人、Agent、资源引用或历史视图；视图不拥有独立事实。

**WikiDocument（Wiki 文档）**：LLM-Wiki 中一个具有稳定逻辑身份的文档对象，例如来源文档、实体、概念或综合内容。WikiDocument 的正文通过多个 WikiRevision 版本保存；更新文档不会覆盖已有正式版本。只有当前 Formal WikiRevision 才能作为正式查询结果。

**WikiRevision（Wiki 文档版本）**：WikiDocument 的一次完整、不可变页面快照，包含分类、标题、可选描述、Markdown 正文、创建信息和可选基准版本；它拥有该版本完整的结构化 Resource Reference 关系。Proposal、候选/正式状态和正式版本指针是关联的治理事实，不是页面正文。正式查询只返回当前 Formal WikiRevision。

**Formal WikiRevision（正式 Wiki 版本）**：已经通过 Proposal 整体审核并被平台正式查询指针选中的 WikiRevision。TerminusDB Commit 只记录存储变化，不能单独证明 WikiRevision 已经正式批准。

**Wiki Metadata（Wiki 页面元数据）**：描述单个 WikiRevision 的页面信息，例如分类（`source`、`entity`、`concept` 或 `synthesis`）、标题、可选描述、文档 ID、版本 ID 和创建时间。可在 Markdown frontmatter 中呈现这些描述信息；Proposal 状态、当前正式版本指针、结构化资源引用、审计记录和访问权限等治理事实以 LLM-Wiki 的结构化记录为准。

**Formal Query（正式查询）**：只读取当前 Formal WikiRevision、正式 Resource Reference 和正式资源版本的查询能力。正式查询不读取草稿或 candidate branch 当前状态。

**Proposal Preview（提案预览）**：在明确 Proposal 上下文中读取 candidate branch 草稿、生成 Diff 和查看影响范围的能力。提案预览与正式查询分离，预览内容带有草稿标记，不能直接参与正式调度或形成正式研究结论。

**Candidate Commit（候选提交）**：由某个 Formal Revision 派生、写入领域 candidate branch 的不可变存储版本。Candidate Commit 只表示候选内容和存储历史，不表示已经正式批准；提交 Merge Request Buffer 后，关联的 candidate head 被锁定为本次正式化审核对象。

**Merge Request Buffer（合并请求缓冲）**：Agent 通过领域管理 MCP 提交的正式化请求，引用一个或多个 Candidate Commit、固定 candidate head、基准 Formal Revision、diff/merge dry-run 结果和候选解决方案。Project Owner 从完整方案中只能选择一个批准或驳回；方案可以是直接采用一个候选，也可以是 `blended` 的新候选结果；它不重复承载领域正文。

**Candidate Resolution（候选解决版本）**：Agent 针对多个冲突 candidate branch 生成的新候选版本。它可以选择某个候选、综合多个候选或放弃部分修改，但不能改写其他提交者的原始 candidate branch 或 Commit。综合多个来源形成的新候选结果称为 `blended`，必须拥有自己的不可变 candidate Commit。

**Partially Blended Submission（部分混合提交）**：来源提交的一部分变更被纳入新的混合候选时，该来源提交的处理结果。原始提交保留为历史记录，不再作为后续正式化的输入；若要继续提交未纳入的内容，需创建新的提交。

**Candidate Disposition（候选处置结果）**：PO 对审核池中来源提交在正式化方案中的处理结果，包括完整采用（`selected`）、与其他来源组合（`blended`）、部分纳入混合候选（`partially blended`）或放弃（`abandoned`）。该结果对应一个已选定并成功正式化的完整候选方案。

**Draft Acceptance Review（草稿接纳审核）**：端侧 Agent 或研究人员提交修改后进行的第一阶段审核，在中央草稿箱内完成。Research Mapping 变更由相关 TaskNode 负责人审核；LLM-Wiki 变更由 Wiki Curator、Resource Owner 或文档负责人审核。审核通过后，由人调用对应的领域管理 MCP，把该草稿写成 candidate branch 的第一个 Commit，形成 WikiRevision 或 Mapping Revision 草稿；该审核不代表内容已经成为正式科研事实。中央 Agent 不参与这一阶段。

> 修订（2026-10-21）：删去「Task Agent 设计稿由 Project Owner 审核」，端侧自持后没有这一类草稿。

**Candidate Pre-Review（候选预审）**：第二阶段审核的初步部分，由 Centre Agent 对**已存在的候选分支**做权限范围、对象冲突和影响范围检查，必要时生成混合候选。格式、对象引用与依赖关系三类确定性检查已前移到领域管理 MCP 在创建候选时拒绝，不再属于预审。它作用在候选上，不作用在草稿上；它不构成批准，也不能代替 Project Owner 的正式发布审核。

> 修订（2026-10-22）：原表述含「结构、引用、依赖」三类检查。这三类改由领域 MCP 写入时拒绝，依据「候选创建的机械校验前置」(ai4-eex0)。

**Pre-Review Report（预审报告）**：Centre Agent 对某个候选在某一确切候选头与判据版本下得出的结论，含逐项检查结果、冲突矩阵与通过或不通过的判定。它以只追加日志写入领域治理记录，唯一键为 `(candidate_id, candidate_head, rule_set_version)`；它不是批准，也不改变 Proposal 状态。Mapping 与 LLM-Wiki 各有自己的报告表，不共享。

**Rule Set Version（判据版本）**：预审判据的版本号。判据本身是受 Git 管理的规则文件；报告只记录版本号与检查项清单，不记录提示词全文，以便事后判断两次结论的差异来自候选变化还是判据变化。版本号无法解析到规则文件时，报告不予写入。

**Pre-Review Report Invalidation（预审报告失效）**：候选头或基准正式版本在报告生成后再次移动时，向判定表追加一条判定（`head_moved` 或 `base_moved`），报告行本身不被修改。「当前有效报告」由同一候选最新的判定推出。失效的报告不能作为批准依据；受影响候选在重算完成前卡住，未受影响的候选照常可批。

**Formal Publication Review（正式发布审核）**：草稿转为正式版本前，由项目负责人进行的第二阶段审核。只有审核通过并更新 Formal WikiRevision 或 Formal Mapping Revision 指针后，内容才能进入正式查询和正式调度。

**Task Node Owner（任务节点负责人）**：对相关 TaskNode 的任务修改、结果和证据进行第一阶段审核的责任人。其审核范围是草稿接纳，不替代项目负责人进行正式发布批准。

**Project Owner（项目负责人）**：对项目正式 Research Mapping、Wiki 内容及其治理变更承担最终审核责任的人，负责草稿转正式版本的正式发布审核。

**LLM-Wiki（大语言模型科研 Wiki）**：面向科研项目的文字知识与证据索引空间。LLM-Wiki 保存研究说明、结构化元数据和对外部科研资源的引用，不保存数据、代码、实验文件等资源本体；其内容可以由人或 Agent 提交，并经过项目治理流程形成正式版本。平台仅参考 Harness Wiki 的 LLM-Wiki 文档分类和治理方式，不将 Harness Wiki 作为本平台的整体存储架构或唯一事实源。

**Resource（科研资源）**：可被本科研项目发现、引用、处理或复用的对象，可以是数字对象、文字内容、计算结果、研究假设、Agent 输出、Skill、MCP 能力或实物；资源不要求必须是文本或计算机可存储对象。

**ResourceVersion（资源版本）**：同一 Resource 在特定时间、来源或内容状态下的不可变版本，保存来源/外部版本标识、记录与生成信息、处理方式及可访问性观察。正式引用必须精确指向 ResourceVersion，以避免资源后续变化悄悄改变历史科研事实。

**RawArtifact（原始资源载体）**：ResourceVersion 对应的文件、数据集、代码快照、实验材料或其他可访问载体的记录；它描述载体的位置、完整性和可访问性，不等于资源本身。

**Resource Reference（资源引用）**：LLM-Wiki 中由一个 WikiRevision 拥有的结构化版本引用，必须精确指向一个 WikiRevision 或 ResourceVersion，不能只指向可变的 WikiDocument、Resource 或“最新版本”。引用保存其角色、来源任务弱引用和可选正文定位；资源定位、来源、生成信息和处理方式由目标 ResourceVersion/RawArtifact 提供，引用本身不复制资源本体或建立独立治理状态机。

**Resource Handling Mode（资源处理模式）**：描述 Agent 或研究人员如何处理被引用资源。Wiki 文档和可直接读取的 raw 资源可以直接查询；实物或其他无法直接读取的资源需要指派研究人员完成观察、实验、测量或其他处理，并将处理结果作为新的可追溯资源或 Wiki 内容提交。

**Resource Reference Status（资源引用状态）**：描述外部资源当前可追踪性的状态，例如 `available`、`unavailable`、`moved`、`superseded` 和 `archived`；资源链接失效不会删除历史引用，但正式视图应提示当前不可用。

## 协作与治理

**Unified Proposal Governance Kernel（统一提案治理内核）**：Research Mapping 与 LLM-Wiki 共享的提案版本治理语义，包括草稿提交与一审、Proposal、candidate branch、candidate Commit、candidate head 锁定、候选预审、Merge Request Buffer、冲突检查和 Formal Revision；它不要求两个领域共享实现、存储、MCP 或审计链。

**Domain Adapter（领域适配层）**：某个领域对统一提案治理内核的独立实现，负责领域专属的 MCP、对象校验、冲突检测、候选存储、正式版本和审计；Research Mapping 与 LLM-Wiki 各自拥有一个领域适配层。草稿箱由两个领域共用，不属于适配层。

**Proposal（变更提案）**：对正式 Research Mapping 或 LLM-Wiki 受治理内容提出的结构化变更请求。Mapping Proposal 只修改 Research Mapping；Wiki Proposal 只修改 LLM-Wiki；第一阶段不存在跨域 Proposal。

**Wiki Proposal（Wiki 变更提案）**：由一个或多个已通过一审的 Wiki 草稿推进而成的 Wiki 治理单元。Wiki Proposal 关联 candidate branch、candidate Commit、Merge Request Buffer、基准 Formal WikiRevision 和正式化结果；它可以包含多个文档变更，但默认整体选择和整体正式化。

**MCP Submission（MCP 提交）**：端侧 Agent 通过标准化 MCP 工具提交任务结果、失败报告或 Proposal 的行为；它是平台接收 Agent 变更的统一入口，不等于正式批准。

**Agent Gateway（Agent 网关）**：一个 Work Agent 里返修处置 MCP 与消息监听两个功能的复合，不是一个独立进程。它只承担人要做的事（返修、放弃、转人工、观察）与出站消息订阅，不下发任务，也不写草稿。task-agent 的网关随任务负责人部署，centre-agent 的网关随中央控制面部署。

> 修订（2026-10-22）：原定义为「为一个 Agent 提供 MCP 入口、消息入口与执行控制边界的常驻进程」。现明确网关是 `gateway/mcp` 与 `gateway/subscriber` 两个组件的复合；执行控制由 Worker Lease 与状态机承担，不另设网关进程。

**Work Agent（工作 Agent）**：Task Agent 与 Centre Agent 的统一上位词。两种实例共用一套架构：返修处置 MCP、消息监听、短生命周期 Worker 三个组件，加一份本地 SQLite、一套 Execution Record 状态机与 Worker Lease。它们只在订阅什么、一轮 loop 做什么、处置面承接什么动作上不同。

_Avoid_: 用 Work Agent 替代 Task Agent 或 Centre Agent 这两个实例名。

**Task Agent（任务 Agent）**：研究员在自己的电脑上编写和运行的 Work Agent 实例，用于执行边界明确、重复、耗时或结构化的科研任务；它不是平台自研的通用 harness，也不由平台部署或托管。它主动连接中央消息队列接收上游交接，按中央服务对端侧开放的能力面调用服务，执行结果作为草稿写入中央草稿箱。

**Agent Definition（Agent 定义）**：一份 Work Agent 在一轮 loop 里要做什么的说明，包括任务指令、允许的模型和允许调用的领域能力。Centre Agent 的定义是固定的预审说明。Task Agent 的定义由研究员在平台给出的样例上修改。它不是 Gateway，也不是 Personal Agent 用来安装套件的 skill。

_Avoid_: 把 Agent 定义叫成服务模板或运行时。服务模板只负责把进程拉起来，运行时是状态机、租约和拉起子进程的实现。

**Centre Agent（中央 Agent）**：部署在中央控制面上的 Work Agent 实例，对 Research Mapping 与 LLM-Wiki 的候选分支做候选预审并生成必要的混合候选。它与 Task Agent 共用架构，但订阅候选事件与正式版本发布事件，处置面当前不提供功能。它不参与草稿的一审、不代替研究负责人进行科研内容判断和最终批准、不写正式版本、不发起执行、不部署或托管 Task Agent。任何正式 Mapping 或正式科研结果发布都必须由 Project Owner 明确批准。

> 修订（2026-10-22）：原条目名为 Central Agent，现统一为 Centre Agent 并明确它是 Work Agent 的中央实例。删去「按 Project Owner 已批准的绑定部署 Task Agent」（2026-10-21）。

**Execution Submission（执行提交）**：Task Agent 一轮执行结束后作为草稿写入中央草稿箱的不可变结果。它不保存在 Gateway 的 SQLite 中，也不称为 Buffer。

> 修订（2026-10-22）：原定义为「提交给 Task Node Owner 审核、保存在 Task Agent Gateway SQLite 中，与审核决定和通知 outbox 同库」。一审现在发生在中央草稿箱，Gateway 只记录 `draft_id`，不再承载待审结果。

**Execution Record（执行记录）**：Work Agent 对一轮 loop 的开始、运行、暂停、失败、完成和人工接管等运行过程的结构化记录，保存在该 Agent 自己的 SQLite 中。它不等于正式 Research Mapping 变更，也不单独授予科研结果正式地位；草稿的审核进度不在其中投影。

> 修订（2026-10-22）：删去「可以由 Central Agent 调度和追加」，调度已取消。

**Worker Lease（Worker 租约）**：Work Agent 在本地 SQLite 中为一个订阅目标（Task Agent 是 `task_node_id`，Centre Agent 是 `candidate_id`）领取短生命周期 Worker 启动权的、可过期的执行协调记录。同一目标同时只能存在一个有效租约；未取得租约的入口不得启动第二个 Worker。它只做本地单实例互斥，不是跨实例的分发租约。

> 修订（2026-10-22）：原条目只覆盖端侧 Task Agent 的 `task_node_id`。统一架构后 Centre Agent 同样持有租约表，目标换成 `candidate_id`，语义仍是本地互斥。

**AuditEvent（审计事件）**：领域内对受控提交、调度、执行、预审、审核、批准、驳回和正式化等操作的不可变过程记录。AuditEvent 至少说明操作者、操作类型、目标、基准版本、结果、时间、原因以及关联的 Proposal 或任务标识，用于按任务、提案、正式版本或时间重建责任链。它属于领域治理记录，由领域服务在写事实的同一事务内产生，各领域各自持有；它不是接口访问记录。

**Call Ledger（调用账本）**：中央对外接口层对每次工具调用的不可变记录，说明套件调用标识、连接通道、被调服务、工具名、目标对象标识、结果与耗时，用于回答「谁通过什么通道访问了什么」。它与 AuditEvent 是两种记录：AuditEvent 回答「谁改了什么正式事实」，调用账本回答「谁调用了什么接口」。调用账本不记业务语义，不含入参正文，只留参数摘要；读写调用都记，写调用按先记录后执行的两阶段记录。

**Suite Call Identifier（套件调用标识）**：调用账本上由调用方套件自行填入的标识。它不经中央校验；多人共用一个套件时会并成同一个标识。它不是 Caller。
_Avoid_: Caller, actor_id

**Caller（调用者）**：向 Gateway 发起 MCP 请求且已通过 Gateway 当前身份校验的请求来源。最小闭环阶段，Caller 由启动配置中的本地开发令牌和调用者标识确定，并作为 OwnerCommand 和 AuditEvent 的操作者记录；它不自动证明调用者是 Task Node Owner，也不授予领域治理权限。它不是调用账本上的套件调用标识。

**Personal Agent（Personal Agent）**：研究人员使用自己的 harness 配置的 Agent，通过 MCP、Skills、系统提示词和 Hooks 接入科研协作平台。

**Agent Registration（Agent 登记）**：Work Agent 部署完成后由部署者写入的一条事实记录，说明该 Agent 的标识、所属主体和部署位置。它不参与鉴权、不阻断调用，只用于事后回答「谁在跑什么 Agent」。

**Central Control（中央控制面）**：部署在中央服务器上的全部服务集合，包括 Research Mapping、LLM-Wiki、草稿箱、Centre Agent、注册表、Web 看板、消息队列与图存储。它不包含任何 Task Agent。

## 人工通知

**人工通知**：提醒某个已登记主体的一条通知。它只表示「要告诉这个人」，不表示任务完成、路线推进或任何领域事实发生变化。
_Avoid_: 把发送成功叫做任务完成

**通知收件人**：一条人工通知所指向的已登记主体。身份是该主体，不是调用方附带的邮箱地址。同一条通知再次提交时，收件人是否相同只看主体是否相同。

收件人的角色由通知类型决定，不由调用方随意指定：交接等待人工处理指向该任务的负责人，路线终点汇总指向项目负责人。
_Avoid_: 邮箱地址、自报地址、由调用方自由选择收件人

**通知正文**：人工通知里写给收件人看的文字。投递服务不判断其中有没有凭据。不把凭据写进去是撰写方的责任。
_Avoid_: 敏感扫描、由投递服务检测密码或令牌

**发件邮箱**：投递服务用来发出全部人工通知的那一个公共信箱。它是部署配置，不是收件人的属性，也不是任何工作人员的个人邮箱。
_Avoid_: 发件人、回复地址、由调用方指定发件邮箱

**投递通道**：发件邮箱背后实际送出邮件的服务器及其加密方式。它属于部署配置，与某一条通知的内容无关；同一封信换一条通道重发，通知本身没有变化。
_Avoid_: 把通道参数写进通知、由调用方传入 SMTP 设置

**投递尝试**：对某一条通知的某一个收件人实际执行的一次发信。它与通知是一对多：一条通知可能因为收件人不同、或因为暂时失败重试，产生多次投递尝试。投递尝试失败不改动任何领域事实。
_Avoid_: 把一次投递尝试叫做一次通知、把重试算作新通知

## 版本与存储

**Mapping Revision（Mapping 版本）**：Research Mapping 在版本化存储中的一个具体版本。FormalRevision 是已经通过负责人审核、可供正式查询的版本；TerminusDB Commit 是其底层存储版本，两者通过平台治理记录关联。

**Formal Mapping（正式 Mapping）**：产品层唯一 Research Mapping 在当前 FormalRevision 上形成的正式查询投影。存储层可以有一个 formal branch 和多个 Proposal candidate branch；candidate branch 不是第二张研究图，普通查询和正式调度只读取 FormalRevision。

**TerminusDB Commit（TerminusDB 提交）**：TerminusDB 中记录一次图状态变化的存储版本；它可以对应草稿或正式数据，只有经过平台治理和负责人批准并关联到 FormalRevision 的 Commit 才能作为正式 Mapping 的版本依据。

**FormalRevision（正式版本）**：经负责人批准、可被普通查询读取的 Mapping 版本标识；它关联对应的 TerminusDB Commit、来源 Proposal 和审核结果。

**Trace（执行痕迹）**：对提交、执行、失败、审核、批准和路线变化等过程事件的记录；它解释 Mapping 如何变成当前状态，但不替代 Mapping 本身。

**Mapping Status（Mapping 状态）**：TaskNode 或 Dependency Edge 版本的治理状态。首版版本状态使用 `candidate`、`formal`、`superseded`、`rejected`、`invalidated`；`ready`、`running`、`awaiting_acceptance` 等属于任务运行投影或 Execution Record，不得与版本状态混用。

**Formal Mapping View（正式 Mapping 视图）**：只展示已批准且有效的 TaskNode 和 Dependency Edge 的查询视图，用于正式进度、依赖判断和任务调度；它不是独立物理图。

**Draft Mapping View（草稿 Mapping 视图）**：展示某个 Proposal 变更应用后的预览结果，可包含尚未批准的节点和边；草稿视图不能触发正式调度或发布正式资源。

**Proposal Preview（提案预览）**：将 Proposal 的结构化变更应用到当前正式 Mapping 后生成的临时视图，用于负责人查看结构 Diff 和影响分析。

**ChangeSet（变更集）**：Proposal 中描述新增、修改、废弃或恢复节点和边的结构化操作集合；它是生成草稿预览和正式提交的机器可读依据。

## 首版状态归属

| 对象 | 研究人员看到的操作 | 首版状态 | 正式化条件 |
| --- | --- | --- | --- |
| TaskNode/DependencyEdge 版本 | 查看路线草稿、比较路线、查看正式路线 | `candidate`、`formal`、`superseded`、`rejected`、`invalidated` | 通过 Proposal 和 Project Owner 的 Formal Publication Review |
| Mapping 草稿 | 提交、修改、查看退回原因 | `drafting`、`submitted`、`accepted`、`rejected`、`promoted`（`under_review` 并发审核保护、`abandoned` 作者放弃草稿，均未实现，首版不支持） | 一审通过后由人调用 Mapping 管理 MCP 写入候选分支 |
| Mapping Proposal | 查看路线变更、影响和审核意见 | `draft`、`candidate`、`mr_ready`、`stale`、`conflict`、`merged`、`rejected`、`abandoned` | 创建新的 Formal MappingRevision |
| Execution Record | 执行、重试、转人工、回答提问、查看草稿 | `queued`、`running`、`waiting`、`completed`、`needs_revision`、`rejected`、`human_takeover`、`failed`、`cancelled` | 首版不单独发布“正式科研结论”；执行完成时草稿已写入中央草稿箱，草稿的审核与正式化属领域治理 |
| TaskNode 运行投影 | 查看“待执行、执行中、待补充、需调整路线” | `not_ready`、`ready`、`in_progress`、`blocked`、`route_change_required` | 由正式 Mapping 和 Execution Record 计算，不覆盖版本状态 |

> 修订（2026-10-22）：Execution Record 原取值含 `succeeded`、`awaiting_acceptance`、`supplement_requested`、`accepted`。一审移到中央草稿箱后，Gateway 不再承载接纳：正常终点为 `completed` 并记录 `draft_id`，TaskNode 运行投影同步删去 `awaiting_acceptance` 与 `accepted`。

## 面向研究人员的首版操作语言

普通用户不需要理解数据库分支或 Commit。首版界面和帮助文案应优先使用以下操作：

1. 创建项目并邀请成员，指定 Project Owner 和每个任务的 TaskNode Owner。
2. 创建任务路线，填写目标、完成条件、输入、预期输出和需要人工判断的环节。
3. 选择负责人或 Agent 执行任务，查看任务是否“待执行”以及前置条件是否满足。
4. 提交结果和证据，查看“执行记录”和“证据来源”，必要时补充材料、重试、转交或请求人工接管。
5. TaskNode Owner 在中央草稿箱里审阅草稿：通过就把该草稿作为候选分支提交，这即是一审通过；不通过就退回并说明原因。执行记录本身不承载接纳。
6. 只有路线、依赖、任务目标或激活条件发生变化时，才点击“创建路线变更草稿”，查看 Diff 和影响范围。
7. Project Owner 查看完整候选、影响范围和审核意见后，选择“批准为正式路线”或“驳回并说明原因”。
8. 研究人员在正式路线、任务进度和审计时间线中查看结果；候选路线不会混入正式查询或正式调度。

这些操作映射到内部的 MCP Submission、Execution Record、Proposal、Formal MappingRevision 和 AuditEvent，但技术对象不应成为普通研究工作流的前置知识。
