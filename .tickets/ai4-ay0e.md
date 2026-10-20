---
id: ai4-ay0e
status: closed
deps: [ai4-9f7i, ai4-ebqx, ai4-e257, ai4-saug, ai4-dy2x, ai4-vbnr]
links: []
created: 2026-10-16T00:37:54Z
type: prototype
priority: 1
assignee: hanjiang
parent: ai4-ru15
tags: [wayfinder:prototype, product, ai4science]
---
# 通用平台的第一阶段产品范围

## Question
如何用有限的第一阶段产品证明平台具备通用科研协作能力？需要确定宏观产品面：用户入口、研究图、任务执行、资源空间、Proposal、审计和展示方式中哪些必须进入首个可演示版本，哪些暂缓。暂不拆实现任务。

## Acceptance Criteria

确定首个可演示版本的一级功能和验证方式；形成从需求地图交给规格设计阶段的边界。

## Notes

**2026-10-17T14:58:26Z**

## Answer

SciWeave 首个可演示版本采用“Research Mapping 驱动的科研任务闭环”作为唯一主线：创建研究任务 → 分派人员或 Agent → 提交执行结果和证据引用 → TaskNode Owner 结果接纳 → 需要改变路线时生成 Mapping Proposal → Project Owner 批准或驳回 → 形成新的 Formal MappingRevision。平台层保持场景中立，具体科研领域通过可替换的示例场景提供演示数据和 Agent 能力。

### 首版必须进入演示的能力

1. **项目入口与角色**：一个科研小组、一个项目、Project Owner、研究成员、Personal Agent 或 Task Agent；不实现复杂组织、跨机构协作或公开 Agent 市场。
2. **Research Mapping**：展示 TaskNode 和 Dependency Edge；能够创建任务、查看依赖、分派责任主体，并从正式 Mapping 生成任务视图。
3. **受控任务执行**：Central Agent 根据已批准的任务和依赖进行分派；Agent 或研究人员提交执行记录、结果摘要、失败报告和证据引用；普通失败支持重试、转交或人工接管。
4. **数字证据引用**：首版只完整演示可直接读取的数字资源或外部版本引用；任务结果和证据必须能追溯到任务、提交者、时间和资源版本。实物处理只保留为 researcher-required 的后续扩展，不实现设备控制或现场采集。
5. **Mapping Proposal**：只有会改变正式 Research Mapping 的路线结构变化进入 Proposal；展示候选 Diff、依赖检查和影响范围。首版只实现单候选、单领域的演示路径，不实现并行候选、blended candidate 或跨域原子正式化。
6. **人工正式审核**：Project Owner 明确批准或驳回会改变 Formal Mapping 的路线变化；任务结果由 TaskNode Owner 接纳，首版不单独建立“正式科研结论”对象，结果通过 Execution Record 和 Resource Reference 追溯。未经 Project Owner 批准的路线候选不得进入正式查询或正式调度。
7. **执行留痕与审计**：展示任务执行、提交、预审、审核、批准、驳回、正式化和失败接管的时间线；审计记录可以按任务、Proposal 或 Formal MappingRevision 回溯责任链。
8. **SciencePal 核心使用**：SciencePal 必须承载至少一个核心科研 Agent、任务流程或结果审核环节，不能只用于展示文案。

同时，首版不单独建立“正式科研结论”对象：TaskNode Owner 负责结果接纳，结果通过 Execution Record 和 Resource Reference 追溯；只有改变 Formal Mapping 的路线结构变化才进入 Project Owner 的 Formal Publication Review。

### 首版明确暂缓的能力

- LLM-Wiki 的独立正式化闭环；首版只将数字证据作为受控引用或结果附件展示；
- ResourceVersion、RawArtifact 等完整资源治理模型；
- Agent/Skill/MCP 能力注册变更的 Proposal；
- 跨 Research Mapping 与 LLM-Wiki 的跨域写入或原子正式化；
- 并行候选、冲突解决、blended candidate、复杂风险分级和自动发布；
- 真实实验设备控制、实物库存、现场采集、复杂权限、多租户和公开生态；
- 完整通用平台实现、生产部署和大规模可靠性验证。

### 首版验证方式

以一个可替换的具体科研示例场景准备可运行演示。示例场景只提供初始 TaskNode、依赖、Agent 能力、数字证据和一条可观察的路线调整，不改变平台领域模型。演示必须至少展示一次 Agent/人员执行、一次证据提交、一次负责人审核、一次失败或路线调整，以及一次 Proposal 正式化或驳回；同时保留操作时间线和结果来源。

首版验收的核心不是覆盖所有学科，而是证明同一套 Research Mapping、任务执行、证据引用、人工审核和 Proposal 机制可以承载不同场景。具体默认示例场景和演示数据另建决策票确定。演示脚本必须分别展示 TaskNode Owner 的结果接纳和 Project Owner 对路线候选的 Formal Publication Review，不能用一次笼统的“负责人审核”替代两步。
