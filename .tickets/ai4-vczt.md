---
id: ai4-vczt
status: open
deps: [ai4-7xtf]
links: []
created: 2026-10-20T13:29:04Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-orpg
tags: [wiki, implementation]
---
# Wiki ResourceVersion 资格审核与撤回纵向实现

实现 LLM-Wiki 对精确 ResourceVersion 的独立资格审核记录，供候选准备、正式查询和正式化校验使用。资源资格审核不替代 Wiki Submission 接纳审核、Wiki 文档/引用审核或 Project Owner Formal Publication Review。

## Design

遵循 [`Wiki 资源审核与跨存储正式化设计`](../docs/superpowers/specs/2026-10-20-wiki-resource-review-cross-storage-formalization-design.md)、[`LLM-Wiki 内容模型`](../docs/superpowers/specs/2026-10-19-llm-wiki-content-model-design.md) 与 [`Wiki 候选治理记录模型`](../docs/superpowers/specs/2026-10-19-wiki-candidate-governance-record-model-design.md)。审核以不可变 `resource_version_id` 为目标，审核记录追加保存；每条决定可追溯 reviewer 身份、Resource Owner 或明确授权来源、结论、理由/证据、时间、使用范围和限制。仅有自由文本审计备注不能代替结构化资格决定。

只有 Resource Owner 或具备可追溯授权的审核人可以作出资源资格决定。审核需记录版本身份/内容快照识别能力、来源与生成信息、许可/署名限制、访问定位及 `handling_mode`；未知项必须显式记录。当前资格由该 ResourceVersion 最近一项有效审核决定及其适用范围确定；拒绝或撤回阻止新的正式化，后续批准可以恢复资格。对外部内容不能固定或无法取得哈希的有限批准，必须保留不可复现限制。

候选可以引用待审或被拒的精确 ResourceVersion，但必须显示其资格状态，且不得呈现为已批准。资格决定不得随 Wiki 文档审核而隐式产生；资源审核撤回不得改写既有正式 WikiRevision 或其精确引用。资格状态应能被其他 Wiki 实现切片按稳定版本 ID 查询；不建立与 Research Mapping 的强关系，不预设未确认的 API、数据库部署形态或运行依赖。

## Acceptance Criteria

- [ ] 资源资格决定以结构化、追加式记录保存，并精确绑定不可变 `resource_version_id`；记录 reviewer、授权来源、批准/拒绝/撤回决定、理由/证据、决定时间及适用范围/限制，并关联审计事件。
- [ ] 仅 Resource Owner 或可验证的明确授权审核人可作出决定；缺少可识别授权时维持待审，拒绝越权决定并留下可审计结果。
- [ ] 审核核对版本身份/快照、来源/生成信息、许可/署名、访问定位和处理方式；未知信息与外部内容未固定限制可被明确记录和呈现。
- [ ] 后续拒绝或撤回阻止该版本用于新正式化；后续有效批准可恢复资格；旧审核记录不被覆盖，内容变更后的新 ResourceVersion 不继承旧决定。
- [ ] 候选及查询集成可按精确版本 ID 获取当前资格状态；待审/拒绝/撤回不会被显示为批准，撤回不重写已正式化 WikiRevision 的引用。
- [ ] 自动化测试覆盖授权/越权、批准/拒绝/撤回/重新批准、版本绑定、范围限制、未知证据和追加审计；无需固定部署端口或真实凭据。
- [ ] 不新增未确认的运行依赖；如实现确需依赖，先更新对应 fer 任务与 `docs/DEPENDENCIES.md`，按所选包管理器声明并锁定后再实现。
