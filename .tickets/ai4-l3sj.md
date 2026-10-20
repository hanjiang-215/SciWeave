---
id: ai4-l3sj
status: closed
deps: []
links: []
created: 2026-10-18T14:54:50Z
type: task
priority: 1
assignee: zhanyunfei
parent: ai4-56iu  # Wiki 持久化模型分支
tags: [wayfinder:grilling]
---
# LLM-Wiki 内容模型与资源引用字段设计

明确 Wiki 内容对象、页面元数据和资源引用的具体领域字段、关系与约束，供后续实现规格使用。

## Design

### 模型边界与对象职责

以下字段名是领域规格名称，不指定 SQLite / TerminusDB 的物理列、ORM、API 或序列化格式。LLM-Wiki 只存文字说明、结构化元数据和引用关系，不存资源本体；跨 Research Mapping 的任务与执行标识仅以弱引用 ID 表示。

- **WikiDocument** 表示稳定逻辑身份：`document_id`（必填、在 LLM-Wiki 领域唯一且不可变）、`created_by`、`created_at`。不在此对象保存可被版本修订的标题、分类、描述或正文。对象与当前正式版本之间有 0..1 个结构化 `current_formal_revision_id` 指针；该指针必须指向属于此文档的 WikiRevision。无正式版本时指针为空。
- **WikiRevision** 表示一个完整、不可变的页面快照：`revision_id`、`document_id`、`category`、`title`、可选 `description`、`body_markdown`、`created_by`、`created_at`、可选 `based_on_revision_id`。首次创建时基准版本为空；对已有页面修订时，基准必须指向该文档当前正式版本。每个版本保存完整正文与完整 Resource Reference 关系，而非补丁。
  - `category` 的初始允许值为 `source`、`entity`、`concept`、`synthesis`；`raw` 文件/数据不是 Wiki 页面分类，而由 ResourceVersion 和可选 RawArtifact 表达。新增分类需扩展受控词汇，不能借用自由文本产生同义分类。
  - 来源通过该版本的结构化 Resource Reference 指向精确的来源 ResourceVersion 或 WikiRevision；来源 URL、外部标识、许可/署名及生成信息归入对应 ResourceVersion，不以非结构化的单一 `source` 字符串替代引用关系。
  - Proposal 关联、candidate/formal 治理状态、TerminusDB Commit 以及正式审核信息是结构化治理事实，不是 Markdown 正文/frontmatter 的事实源。WikiRevision 可关联所属 Proposal 和治理状态，但本票不改变其既有生命周期定义。
- **Resource** 表示稳定资源身份：`resource_id`（必填、唯一且不可变）、稳定的 `resource_type`、`created_by`、`created_at`，可选 `owner_id`。资源类型使用受控且可扩展的领域词汇，覆盖数据/代码/文字内容/计算结果/研究假设/项目 Agent 输出/Skill/MCP 能力/实物；项目初始化阶段供平台自身管理使用的基础 Skill/MCP 不纳入科研资源。资源类型若发生实质变化，应新建 Resource，而不是改写已有资源身份。
- **ResourceVersion** 表示该 Resource 的不可变内容与来源版本：`resource_version_id`（必填、唯一且不可变）、`resource_id`、可选版本显示标签、可选版本描述、可选 `source_locator`、`source_external_id`、`external_version_id`、可选 `current_access_locator`、`recorded_by`、`recorded_at`、可选 `generated_at`、可选 `generated_by`、可选 `generated_by_task_id`、可选 `license`、`attribution`、可选内容快照哈希算法和值、`handling_mode`、输入 ResourceVersion 关系，以及可选可访问性状态和最近检查时间。可访问性状态首次检查前可为空；一旦记录状态，必须同时记录检查时间。`current_access_locator` 是可变可访问性观察；迁移它不能改写原始来源、内容哈希或版本 ID。若不能确认迁移后内容仍与原版本一致，必须新建 ResourceVersion。任务 ID 是指向 Mapping 域的弱引用。除可访问性状态、检查时间和当前访问定位外，版本字段及来源快照不可原地改写；外部可访问性是随时间变化的状态观察，不改变版本内容或其哈希。
  - `external_version_id` 用于记录上游不可变版本标识（如 DOI 版本或数据集发布号）；若没有上游版本标识，可记录稳定定位和可得的内容快照哈希。外部既无版本标识又无法固定/哈希快照时，内部 `resource_version_id` 只标识本次引用记录，不保证外部内容本身不会变化；需由维护者更新引用状态或创建新的 ResourceVersion，不能声称已固定外部内容。
  - `handling_mode` 为 `direct_query` 或 `researcher_required`。直接可读取的文档/数字资源可设为前者；实物或无法直接读取的资源设为后者。后者应提供可操作的处理说明或人工定位信息。
  - 可访问性状态采用既有词汇 `available`、`unavailable`、`moved`、`superseded`、`archived`，并记录可选 `availability_checked_at`。失效/迁移不删除历史版本，也不使引用自动跳转到其他版本。
- **RawArtifact** 是可选的载体元数据：`artifact_id`（唯一）、`resource_version_id`、外部 `locator`/受控访问定位、`media_type`、可选 `size_bytes`、`checksum_algorithm` 与 `checksum_value`。它不保存文件本体；不以机器本地绝对路径作为业务定位。对于有字节内容的文件载体必须记录成对的哈希算法和值；非文件、实物或无 raw 载体的 ResourceVersion 不要求存在 RawArtifact。
- **Resource Reference** 是某个 WikiRevision 拥有的结构化引用记录：`reference_id`、`source_revision_id`、`target_wiki_revision_id` 或 `target_resource_version_id`（恰好一个）、必填的 `reference_role`、可选正文定位/片段、可选 `source_task_id`、`created_by`、`created_at`。`reference_role` 使用受控可扩展词汇，初始可含 `source`、`evidence`、`input`、`related`、`derived_from`。
  - Resource Reference 指向 ResourceVersion 时，定位、来源、生成信息及处理方式从目标 ResourceVersion/RawArtifact 获取，不复制资源本体或可变 URL；Reference 的有效审阅/正式状态随所属 WikiRevision 和既有 Proposal 治理确定。它不另建一套独立状态机。
  - Resource Reference 的可用性是目标版本状态的查询投影：目标资源迁移、失效或归档时展示相应状态，但保留原目标 ID。若指向 WikiRevision，则其可解析性/历史正式性由目标版本的结构化记录判断。

### 关系与完整性约束

- 一个 WikiDocument 可有多个 WikiRevision；一个 WikiRevision 必须且只属于一个 WikiDocument。其 `based_on_revision_id` 若非空，必须指向同一文档先前正式化的版本。一个文档至多有一个当前正式版本指针，该指针必须指向同文档中已经正式化的版本；历史正式版本不被覆盖或删除。
- 一个 Resource 可有多个 ResourceVersion；一个 ResourceVersion 必须且只属于一个 Resource。每个 ResourceVersion 可对应零个或多个 RawArtifact；每个 RawArtifact 必须且只属于一个 ResourceVersion。
- 一个 WikiRevision 可拥有零个或多个 Resource Reference。一个引用必须绑定一个源 WikiRevision，并且 `target_wiki_revision_id` 与 `target_resource_version_id` 必须恰有一个非空；目标必须存在于 LLM-Wiki 领域并精确到不可变版本，禁止只指向 WikiDocument、Resource 或“最新版本”。
- ResourceVersion 的输入关系只指向存在的 ResourceVersion；不允许自引用或形成循环依赖。跨 Mapping 域的 TaskNode / Execution Record 只保存 ID，不建立跨库对象关系。
- 身份 ID 在 LLM-Wiki 领域内唯一且不可复用；作为其他领域弱引用目标时，必须与领域标识共同解释，不要求跨领域共用身份空间。不得原地更新 WikiRevision 的分类、标题、描述、正文、基准或引用边；任何内容/引用更改都创建新 WikiRevision。不得原地覆盖 ResourceVersion 的内容或原始快照；更新资源内容必须创建新 ResourceVersion。引用只有在角色、目标版本或正文定位均相同才视为重复；同一目标因角色或正文片段不同可以被同一版本多次引用。
- 正式化校验要求所有引用目标可解析：目标 WikiRevision 必须已经正式化，或属于同一待正式化完整方案并随源版本一同通过审核；不得引用其他 Proposal 的候选 WikiRevision。目标 ResourceVersion 必须是已存在的精确版本 ID，且必须已由对应资源治理流程批准，或纳入同一完整待正式化方案并完成所需资源审核；资源正式资格从其治理记录派生，不在本模型中另建独立状态机。文档/版本/引用的正文表达可以由 Markdown frontmatter 或 wikilink 呈现，但结构化对象和关系是权威事实，渲染或 lint 应能发现不一致。
- 若文件载体存在，RawArtifact 的哈希算法与哈希值必须同时存在；字节载体的哈希用于发现内容变更，不可在原地更新后仍沿用同一 ResourceVersion。定位变化不得改变引用目标版本。

### 正式查询边界

普通正式查询从每个 WikiDocument 的当前正式版本指针读取 WikiRevision，只返回其完整正文、版本元数据和 Resource Reference；不读取草稿或 candidate branch。引用解析必须使用 Reference 中记录的精确 WikiRevision / ResourceVersion ID，不得静默改指目标文档或资源的最新版本。被引用的历史正式 WikiRevision 可以作为明确的历史引用目标解析，但不能替代其所属文档的当前正式查询结果。ResourceVersion 当前不可访问时仍返回引用和不可用提示；候选治理与 Proposal 预览沿用既有规则并保持明确的草稿上下文。

## Question

WikiDocument、WikiRevision、Resource、ResourceVersion、RawArtifact 与 Resource Reference 分别应承载哪些内容字段和关系？请明确：

- Wiki 文档分类、稳定身份、标题/描述/正文及来源信息分别属于哪个对象；
- 页面元数据与版本内容如何组织，哪些字段是文档级信息、哪些属于单个 WikiRevision；
- Resource、ResourceVersion、RawArtifact 和 Resource Reference 的内容职责及引用关系；
- 正式引用如何指向不可变 WikiRevision 或 ResourceVersion，以及字段约束和引用完整性要求。

## Notes

Wiki 的 Proposal、candidate branch、candidate Commit、Formal WikiRevision 指针和审核生命周期已经由既有决策确定：沿用统一提案治理语义，同时保持 Wiki 领域隔离。本票只决定内容对象与资源引用的字段模型，不重新讨论版本治理状态机、候选正式化规则、API 或代码实现。

## Scenario Validation

1. **新增文档**：分配新的 `document_id` 和首个 `revision_id`；版本具有分类、标题、Markdown 正文及完整引用集合，`based_on_revision_id` 为空。它进入候选前/候选中的草稿阶段时不设置当前正式指针，正式查询不返回草稿；通过既有正式审核后，文档指针才指向该版本。
2. **修订内容或分类**：在同一 `WikiDocument` 下创建新 `WikiRevision`，`based_on_revision_id` 指向当前正式版本，完整保存更新后的标题/分类/描述/正文与引用集合。旧版本不变；新版本正式审核前，正式查询仍返回旧版本。
3. **变更引用**：创建新版本并为其保存完整的新引用集合；每条引用指向明确的目标 `WikiRevision` 或 `ResourceVersion`。被删除的关系只从新版本移除，旧版本仍保留原关系。目标不存在、目标 ID 不是版本级 ID，或目标属于其他未选 Proposal 时，正式化校验失败；同一完整方案内共同正式化的目标允许通过校验。
4. **资源内容更新**：为同一 `Resource` 创建新的 `ResourceVersion` 和新的载体哈希/来源记录；旧版本与现存引用不改指向。外部可访问性改变只更新对应版本的可访问性观察，并在引用中提示，不更改内容哈希或目标 ID。
5. **正式查询**：从每份文档的当前正式版本指针读取；只解析该版本记录的引用目标。若引用目标是曾正式化但后来被替代的历史 `WikiRevision`，解析为该历史版本并标明其版本身份；若目标 `ResourceVersion` 当前不可用，仍返回原引用与状态提示，不自动替换为最新版本。任何 candidate 草稿都不进入普通正式查询。

## Acceptance Criteria

- [x] 形成 WikiDocument、WikiRevision、Resource、ResourceVersion、RawArtifact 与 Resource Reference 的字段和关系清单。
- [x] 说明字段定义、文档级/版本级归属、必要约束，以及正式引用精确指向不可变版本的方式。
- [x] 以新增文档、修订内容、变更引用、资源版本更新和正式查询场景检查模型一致性。

## Progress

领域字段与关系设计已写入本工单，并整理为 `docs/superpowers/specs/2026-10-19-llm-wiki-content-model-design.md`。设计已按用户批准的方向完成，并经用户复核通过；本工单已关闭。后续 Wiki 持久化模型分支的候选治理记录仍由 `ai4-hkdz` 跟踪。

**2026-10-19T08:12:46Z**

用户于 2026-10-19 批准书面领域规格。字段、关系、完整性约束和新增文档、修订、引用变更、资源更新、正式查询场景均已完成；规格见 docs/superpowers/specs/2026-10-19-llm-wiki-content-model-design.md，GLOSSARY.md 已同步相关定义。验证已通过：依赖图无环、git diff --check、设计文档 lint 无诊断。后续 Wiki 持久化模型分支的候选治理记录仍由 ai4-hkdz 跟踪，本票不启动该后续工作。
