---
id: ai4-aaff
status: open
deps: [ai4-ay0e]
links: []
created: 2026-10-17T14:58:26Z
type: prototype
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:prototype, product, sciencepal, ai4science]
---
# SciWeave 默认科研示例场景与验证证据

为 SciencePal 参赛演示选择一个具体、可运行、可验证且不改变 SciWeave 场景中立核心的科研示例场景，明确初始 Research Mapping、数字证据、Agent/人员执行步骤、路线变化和验收证据。

## Design

采用“场景中立核心 + 一个可替换示例场景”。示例场景只负责提供初始 TaskNode、Dependency Edge、Agent/人员执行内容和数字证据，不新增领域专属核心对象，也不改变 SciWeave 的 Research Mapping、Execution Record、Resource Reference 或 Mapping Proposal 语义。

场景选择必须同时满足以下约束：

- 使用公开、可访问、合规且体量可控的数字数据或证据，不依赖真实个人信息、私有账号、现场设备或不稳定的外部服务；
- 能在 5—10 分钟演示中形成 3—6 个有明确依赖的 TaskNode，并至少包含一个人员判断点和一个 Agent/SciencePal 可稳定执行的结构化步骤；
- 能提供可核验的输入、预期输出、来源或版本标识，使结果可以通过 Resource Reference 追溯；
- 能注入一次可观察的执行失败、证据不足或前置条件不满足，并明确区分普通重试/转交与必须改变路线的 Mapping Proposal；
- 能用同一套通用字段表达初始路线、执行记录、结果审核、路线 Diff、Project Owner 决策和正式化结果；
- 不把生物、材料、健康或其他学科概念写入平台核心对象，场景专属内容只存在于示例数据、任务说明、Agent 能力和验收脚本中。

场景决策以“可运行性、证据可追溯性、失败可演示性、SciencePal 可承载性、跨场景替换成本”作为评估维度。未完成评估前保留候选，不在需求地图或术语表中把某个学科写成默认事实。

## Acceptance Criteria

- [ ] 明确一个默认科研示例场景、目标科研痛点、适用角色和可替换边界。
- [ ] 提供初始 Research Mapping：TaskNode、Dependency Edge、负责人/Agent、输入输出、完成条件和至少一个数字 Resource Reference。
- [ ] 提供可访问的最小数字数据或证据包，并记录来源、版本标识、访问限制和替代数据方案。
- [ ] 定义一条可复现的演示脚本：任务执行、结果提交、数字证据引用、TaskNode 负责人审核、失败或路线调整、Mapping Proposal、Diff/影响预览以及 Project Owner 批准或驳回。
- [ ] 明确 SciencePal 承载的核心 Agent、任务流程或结果审核环节，并说明人工接管点。
- [ ] 证明演示只依赖通用 TaskNode、Dependency Edge、Execution Record、Resource Reference 和 Mapping Proposal，不新增领域专属核心对象。
- [ ] 记录一次成功路径和一次失败/驳回路径的可观察证据，包括执行记录、审计时间线、Proposal 状态和 Formal MappingRevision 结果（如批准）。
- [ ] 给出将同一闭环替换到另一科研场景时需要替换的配置和数据清单，证明核心流程不依赖当前示例学科。
