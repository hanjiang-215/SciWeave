# LLM-Wiki 内容模型与资源引用设计

日期：2026-10-19
关联工单：[`ai4-l3sj`](../../../.tickets/ai4-l3sj.md)
状态：设计已获用户批准，等待书面规格复核

## 目的与边界

本设计收敛 LLM-Wiki 内容对象、页面元数据、资源版本和资源引用的领域字段、关系及完整性约束，供后续持久化规格使用。字段名是领域概念，不指定 SQLite / TerminusDB 的物理结构、ORM、API 或序列化格式。LLM-Wiki 保存文字说明、结构化元数据和引用，不保存数据、代码或实验文件本体；Research Mapping 的任务和执行记录只以稳定 ID 弱引用，不建立跨领域对象关系。

Proposal、candidate branch、candidate Commit、Merge Request Buffer、Formal WikiRevision 指针和审核生命周期继续使用既有 Wiki 决策。本设计不改变治理状态机，不扩大首版产品范围。

## 已确认的设计选择

1. **结构化对象分离**：稳定身份、不可变内容版本、资源身份、资源版本、载体元数据和版本级引用分别表达。相比把所有信息塞进 Markdown/frontmatter，这样可以检查引用目标、保留版本历史，并避免页面描述与治理事实混杂。
2. **文档描述随版本变化**：`WikiDocument` 只保存稳定身份；分类、标题、描述、正文和页面来源关系归属 `WikiRevision`。分类变更与内容修订一样生成新版本。
3. **正式引用版本化**：引用目标必须是精确的 `WikiRevision` 或 `ResourceVersion`，不得动态解析为“当前最新版本”。目标内容变化不能悄悄改写历史引用。
4. **描述元数据与治理事实分离**：Markdown frontmatter 可呈现页面描述字段，结构化关系和治理记录才是事实源。Proposal 状态、正式版本指针、访问控制和审核记录不由 frontmatter/wikilink 承担。
5. **沿用最小资源治理**：Resource Reference 随所属 WikiRevision 和既有提交/审核流程治理，不为每个资源对象另造状态机。资源可访问性是版本的可变观察值，不会改写不可变内容版本，也不改变引用目标。

## 对象字段

### WikiDocument

表示一个稳定的 Wiki 页面逻辑身份。

- `document_id`：必填、在 LLM-Wiki 领域内唯一且不可变。
- `created_by`、`created_at`：创建主体和创建时间。
- `current_formal_revision_id`：可为空；非空时必须指向属于该文档且已经正式化的 WikiRevision。文档可以暂时没有正式版本；一个文档至多有一个当前正式版本指针。

标题、分类、描述、正文不属于 WikiDocument，因为这些内容可以修订。

### WikiRevision

表示一个完整且不可变的页面快照，包括其完整结构化引用集合，而非内容补丁。

- `revision_id`：必填、唯一且不可变。
- `document_id`：必填，唯一所属 WikiDocument。
- `category`：必填受控词汇，首期值为 `source`、`entity`、`concept`、`synthesis`。扩展分类需扩展词汇表；禁止以任意自由文本制造同义分类。`raw` 文件/数据不是页面分类，由资源对象和可选 RawArtifact 表达。
- `title`：必填页面标题。
- `description`：可选页面描述。
- `body_markdown`：必填 Markdown 正文。
- `created_by`、`created_at`：版本创建主体和创建时间。
- `based_on_revision_id`：可选基准版本；首个版本为空，现有文档的修改版本指向其所基于的正式版本。
- 来源关系：通过属于该版本的 Resource Reference 指向精确的来源 ResourceVersion 或 WikiRevision。外部来源标识、来源定位、许可/署名和生成信息归目标 ResourceVersion，不以一个自由文本 source 字段替代结构化关系。
- Proposal 关联、候选/正式状态、TerminusDB Commit、审核结果和正式指针是结构化治理事实，不是正文/frontmatter 的真相。WikiRevision 可关联所属 Proposal 和治理状态，但由既有治理规则决定其生命周期。

### Resource

表示稳定的科研资源身份。

- `resource_id`：必填、在 LLM-Wiki 领域内唯一且不可变。
- `resource_type`：必填、稳定且受控可扩展的领域类型；覆盖数字数据、代码、文字内容、计算结果、研究假设、项目 Agent 输出、Skill、MCP 能力或实物。
- `created_by`、`created_at`：创建主体和创建时间。
- `owner_id`：可选资源责任主体标识。

项目初始化时用于管理平台自身的基础 Skill/MCP 不纳入科研资源空间。资源类型若发生实质变化，应建立新 Resource，而不是改写已有资源身份。

### ResourceVersion

表示一个 Resource 的不可变内容/来源版本。

- `resource_version_id`：必填、唯一且不可变。
- `resource_id`：必填所属 Resource。
- `version_label`、`description`：可选版本展示标签和描述。
- `source_locator`、`source_external_id`、`external_version_id`：可选的原始来源定位、外部标识和上游版本标识；属于版本 provenance，不因服务端迁移而被改写。
- `current_access_locator`：可选的当前访问定位，属于可变可访问性观察；发生迁移时更新该定位和 `availability_status` / `availability_checked_at`，但不得修改原始来源定位、资源内容哈希或 `resource_version_id`。若无法确认迁移后的内容仍与原版本一致，则不可把新定位视为同一 ResourceVersion，应创建新版本。
- `recorded_by`、`recorded_at`：记录主体和记录时间。
- `generated_at`、`generated_by`、`generated_by_task_id`：可选生成时间、生成者和来源任务；任务 ID 是 Research Mapping 域的弱引用。
- `license`、`attribution`：可选许可证与署名信息。
- `content_checksum_algorithm`、`content_checksum_value`：可选固定内容快照的哈希算法和值。
- `handling_mode`：必填 `direct_query` 或 `researcher_required`。无法直接读取的实物等资源使用 `researcher_required`，并应提供处理说明或人工定位信息。
- 输入来源：可有零个或多个输入 ResourceVersion 关系，全部指向已存在的精确版本。
- `availability_status`、`availability_checked_at`：当前可访问性观察和最近检查时间。首次检查前两者可以都为空；记录状态后两者必须同时有值。状态沿用 `available`、`unavailable`、`moved`、`superseded`、`archived`。

内容、来源快照和版本身份不可原地改写。上游有不可变版本标识时记录它；没有时尽可能固定定位和内容哈希。如果外部内容既没有版本标识，也无法固定或哈希快照，内部 `resource_version_id` 只证明本平台记录了一次引用，不能声称外部内容本身已被固定。可访问性状态、检查时间及当前访问定位可以按实际状态变化更新，但不能改变版本内容或其哈希；若外部定位变化后无法确认内容未变，则创建新的 ResourceVersion。资源失效、迁移或归档不会删除历史事实，也不触发引用自动跳转。

### RawArtifact

可选的载体元数据，不是资源本体。

- `artifact_id`：必填唯一标识。
- `resource_version_id`：必填所属 ResourceVersion。
- `locator`：外部或受控访问定位，不得使用机器本地绝对路径作为业务标识。
- `media_type`：必填载体媒体类型。
- `size_bytes`：可选字节大小。
- `checksum_algorithm`、`checksum_value`：对字节载体必填且必须成对出现。

一个 ResourceVersion 可关联零个或多个 RawArtifact。实物或没有可存取文件载体的资源不要求创建 RawArtifact。载体的访问定位变化不能改变引用所指的 ResourceVersion；若文件内容变了，应创建新的 ResourceVersion 和哈希，而非覆盖原版本。

### Resource Reference

属于某个 WikiRevision 的结构化引用记录。

- `reference_id`：必填唯一标识。
- `source_revision_id`：必填拥有此引用的 WikiRevision。
- `target_wiki_revision_id` 或 `target_resource_version_id`：必须且只能设置其中一个。
- `reference_role`：必填受控可扩展词汇；初始可包括 `source`、`evidence`、`input`、`related`、`derived_from`。
- `body_locator`：可选正文定位或片段。
- `source_task_id`：可选 Research Mapping 任务弱引用。
- `created_by`、`created_at`：建立引用的主体和时间。

引用指向 ResourceVersion 时，资源定位、来源、生成、许可、处理方式和当前可访问性由目标版本/RawArtifact提供，不在引用记录重复维护可变副本。引用的审核和正式状态由其所属 WikiRevision 的既有 Proposal 治理决定，不另建独立状态机。引用可用性是目标状态的查询投影；目标失效时保留原 ID 并展示状态。

重复引用按 `(source_revision_id, target_version_id, reference_role, body_locator)` 判断；同一版本可因角色或正文定位不同而多次引用同一目标。

## 关系与完整性约束

- 一个 WikiDocument 可以有多个 WikiRevision；每个 WikiRevision 必须且只属于一个 WikiDocument；其 `based_on_revision_id` 非空时必须指向该文档先前正式化的版本。
- 一个 Resource 可以有多个 ResourceVersion；每个 ResourceVersion 必须且只属于一个 Resource。
- 一个 ResourceVersion 可以有零个或多个 RawArtifact；每个 RawArtifact 必须且只属于一个 ResourceVersion。
- 一个 WikiRevision 可以拥有零个或多个 Resource Reference；每条引用必须恰有一个源 WikiRevision 和一个精确目标版本。
- `target_wiki_revision_id` 与 `target_resource_version_id` 互斥且至少一个非空。禁止引用只指向 WikiDocument、Resource 或隐式“最新版本”。目标必须存在并属于 LLM-Wiki 领域。
- 输入 ResourceVersion 关系必须指向存在的版本，不得自引用或形成循环依赖。
- ID 在 LLM-Wiki 领域内唯一且不复用；被其他领域引用时，需结合领域标识解释，不要求跨域共享 ID 空间。跨 Research Mapping 的 TaskNode/Execution Record 只保留弱引用 ID。
- WikiRevision 的分类、标题、描述、正文、基准和引用关系不可原地修改；内容或引用变更创建新的完整 WikiRevision。ResourceVersion 的内容/原始快照也不可覆盖；资源内容变化创建新 ResourceVersion。
- 正式化校验所有目标均可解析。目标 WikiRevision 必须已经正式化，或属于同一个待正式化完整方案并和源版本一起通过审核；不得引用其他 Proposal 的候选 WikiRevision。目标 ResourceVersion 必须是已存在的精确版本 ID，且必须已由对应资源治理流程批准，或纳入同一完整待正式化方案并完成所需资源审核；资源正式资格从其治理记录派生，不在本模型中另建独立状态机。
- 对应的 Markdown frontmatter 和 wikilink 可呈现描述信息或便于阅读；结构化字段与关系始终为权威事实源，渲染或 lint 应能发现正文链接与结构化关系不一致。

## 查询边界

普通正式查询从 WikiDocument 的当前正式版本指针读取 WikiRevision，并返回该版本完整正文、页面元数据和引用集合；不读取 candidate branch 或草稿。引用解析使用记录的精确版本 ID，不得自动解析成最新版本。引用到被替代但曾正式化的历史 WikiRevision 时，可明确返回该历史版本；它不取代目标文档的当前正式查询结果。被引用 ResourceVersion 当前不可访问时，仍返回原引用并提示状态。提案预览继续要求显式 Proposal 上下文，并标记为草稿。

## 场景一致性检查

1. **新增文档**：新建 `document_id` 和首个 `revision_id`；版本有分类、标题、正文和完整引用集合，`based_on_revision_id` 为空。草稿不设置当前正式指针，正式查询不返回；经既有审核正式化后更新指针。
2. **修订正文或分类**：同一个 WikiDocument 下创建新 WikiRevision，基准指向当前正式版本，完整保存新标题/分类/描述/正文和引用关系。旧版本不变；新版本正式化前，正式查询仍返回旧版本。
3. **变更资源引用**：创建新的 WikiRevision 和完整引用集合；新增目标固定为精确的 WikiRevision 或 ResourceVersion，删除的关系只从新版本移除。旧版本仍保留原引用。目标不存在、不是版本级 ID 或指向其他 Proposal 的候选 WikiRevision 时，正式化失败；同一完整方案内一起正式化的目标可通过校验。
4. **更新资源内容**：同一 Resource 下创建新的 ResourceVersion，附上新来源/快照哈希；已有引用继续指向旧版本。仅可访问性变化更新状态观察，不改哈希或目标 ID；查询展示不可用提示。
5. **正式查询**：只读文档当前正式版本和它的精确引用目标。历史正式 WikiRevision 按历史目标解析。candidate 草稿不进入正式结果，ResourceVersion 不可用时不自动换成新版本。

## 排除范围

本设计不定义 SQLite/TerminusDB DDL、ORM、API、文件服务部署、跨存储一致性/恢复协议、访问权限策略、资源状态机扩展或跨域原子事务；这些内容属于其他工单或后续架构决策。
