---
id: ai4-saug
status: in_progress
deps: [ai4-9f7i]
links: []
created: 2026-10-16T00:37:54Z
type: research
priority: 1
assignee: qiyueran
parent: ai4-ru15
tags: [wayfinder:research, product, ai4science]
---
# 科研公共资源与证据空间

## Question
平台需要共享和沉淀哪些科研资源？需要研究并形成宏观范围：文献、数据、代码、实验结果、图表、研究假设、Agent 输出、Skills、MCP 能力和审计记录之间如何作为公共资源被发现、复用和追溯。暂不讨论具体存储技术。

## Acceptance Criteria

形成公共资源和证据空间的一级功能清单；明确资源共享、来源追踪、版本和可复现性的产品范围。

## Notes

**2026-10-16T07:02:28Z**

本轮讨论决策记录：
- 采用 LLM-Wiki 作为项目级科研知识与证据索引，只保存文字说明、结构化元数据和外部资源引用，不保存数据、代码或实验文件本体。
- Resource Reference 定义为一条结构化外部资源引用记录，包含资源类型、外部定位、版本、来源任务、创建者、生成时间、输入资源、治理状态和引用关系。
- Q3 接受：Wiki 文档和 Resource Reference 采用 draft -> submitted -> approved/rejected -> superseded/archived 生命周期，但不同对象的批准含义不同。
- Q6 接受：优先记录不可变外部版本；无法保证时由资源维护人及时更新 Wiki，平台记录引用状态并提示链接变化或失效。
- Q7 接受：LLM-Wiki 作为资源发现主入口，支持跨资源协作和从 Mapping、TaskNode、Proposal 进入引用视图。
- Q8 接受：资源链接失效不删除历史引用，使用 available/unavailable/moved/superseded/archived 等状态提示当前可用性。

**2026-10-16T08:55:16Z**

本轮 Wayfinder 讨论形成的阶段结论：
- 参考 Harness Wiki 的内容组织方式，将 raw、source、entity、concept、synthesis 等内容重建为 TerminusDB-Wiki 中的领域对象和关系，不直接采用现成 Harness Wiki 的 MCP 或存储实现。
- raw 文件由中央节点服务所在机器负责保存和提供访问；TerminusDB 保存 Resource、ResourceVersion、RawArtifact 名片、来源关系、治理状态和访问定位。文件本体不以中央机器的绝对路径作为业务标识。
- TerminusDB-Wiki 的 MCP 作为受控访问入口，按 resource_id 和 version_id 提供元数据查询、受限文本读取和 raw 下载能力；大文件优先返回受控下载句柄或流式能力，不直接塞入 Agent 上下文。
- Research Mapping 与 TerminusDB-Wiki 共用 Proposal、Trace/AuditEvent 和负责人审计链；Mapping Revision 与 Wiki Revision 分开，TerminusDB Commit 只表示存储状态变化，不单独表示科研内容已经批准。
- raw 文件可用性状态与 Wiki 文档、Resource Reference 的治理状态分开管理；上传成功不等于资源批准，文件版本不可覆盖，只能新增版本并保留哈希和来源。

**2026-10-17T01:07:05Z**

Q2 治理决策确认：TerminusDB 作为 Wiki 文档正式事实源，Wiki 文档正文统一使用 Markdown。WikiDocument 保持稳定逻辑身份，修改或创建都生成新的不可变 WikiRevision，不覆盖已有正式版本；候选版本写入 Proposal 对应的 TerminusDB candidate branch，并通过 Commit 保留存储历史。正式 MCP 只读取当前 Formal WikiRevision；文档存在草稿时返回最新正式版本，只有草稿时返回无正式版本，不返回草稿。一个 Proposal 修改多个 Wiki 文档时整体审核、整体正式化。TerminusDB Commit 仅表示存储变化，不单独表示内容已批准。

**2026-10-17T01:10:00Z**

Q2.4-Q2.6 决策确认：Markdown frontmatter 仅展示页面描述性元数据，Proposal 状态、Formal WikiRevision 指针、ResourceVersion 关系、RawArtifact 哈希、权限、审计、candidate branch 和 Commit 等治理事实以 TerminusDB 结构化记录为准。Markdown wikilinks 用于阅读和导出，TerminusDB 结构化关系是引用事实源，不一致时以结构化关系为准并由 lint 检查。正式查询与草稿预览分离：正式查询只读 Formal WikiRevision 和正式资源版本，不读草稿或 candidate branch；预览必须带 Proposal 上下文，只读对应候选分支并明确标记 draft，不能参与正式调度或形成正式研究结论。

**2026-10-17T01:22:20Z**

Q2.9a/Q2.9b 治理分工确认：Wiki 和 Research Mapping 都采用两阶段审核。端侧 Agent 提交修改后，先进入 Buffer，由相关 TaskNode 负责人进行草稿接纳审核；审核通过后才写入 TerminusDB candidate branch，形成 WikiRevision 或 MappingRevision 草稿。草稿转正式版本时，由 Project Owner 进行 Formal Publication Review；只有通过后才更新 Formal WikiRevision 或 Formal MappingRevision 指针，进入正式查询和正式调度。端侧 Agent 可以提出修改，不能替代任务节点负责人或项目负责人完成审核。
