---
id: ai4-7xtf
status: closed
deps: []
links: []
created: 2026-10-20T08:32:17Z
type: task
priority: 1
assignee: hanjiang
parent: ai4-orpg
tags: [wiki, specification, implementation]
---
# Wiki 资源审核与跨存储正式化前置规格

收敛 LLM-Wiki 正式持久化和正式化实现所需的领域决策。已有 Wiki 内容模型规定 ResourceVersion 需经过资源治理审核，但尚未规定审核依据、证据如何绑定精确不可变 ResourceVersion 及其如何决定正式引用资格；Mapping 的 ai4-azx2 规则针对 Mapping，不能直接替代本规格。

## Design

在已关闭的 Wiki 内容模型、Proposal 生命周期、SQLite 治理模型和统一治理语义基础上，独立决定：ResourceVersion 在被正式 WikiRevision 引用前必须满足的审核事实、责任角色/授权来源及可审计证据；Wiki 自身的 TerminusDB/SQLite（或经确认的其他持久化边界）正式化顺序、成功边界、部分失败状态、稳定操作身份、重试/幂等、恢复/对账和查询权威。明确通知是否影响成功、候选/未完成内容如何隔离、查询不一致时的结果。必须说明哪些共通原则可复用，哪些 Mapping 专属语义不可移植。不得预设 Wiki 与 Mapping 共用存储、MCP 或跨域原子事务。

领域决策与失败恢复细节见 [`Wiki 资源审核与跨存储正式化设计`](../docs/superpowers/specs/2026-10-20-wiki-resource-review-cross-storage-formalization-design.md)。本工单仅收敛领域规则，不实现 API、数据库 Schema、代码或运行依赖。

### 已确认：资源版本与文档引用分开审核

- Resource Owner 或其明确授权的审核人，针对精确且不可变的 ResourceVersion 作出资源资格决定；决定记录审核人、授权依据、结论、理由/证据、ResourceVersion ID 和时间。
- 每项资源审核作为独立的追加式审核记录保存，字段至少包括 `resource_version_id`、审核人身份、授权来源、批准/拒绝结论、理由或证据引用及决定时间。审核应核对：版本身份和内容快照是否足以识别、来源/生成信息是否可追溯、许可与署名限制是否明确（未知项须显式标为未知）、访问定位或人工处理要求是否清楚。此审核决定资源版本是否满足治理上的正式引用资格，不替代对科学质量的同行评审。
- 若外部资源没有稳定上游版本 ID 且无法取得内容快照哈希，资源审核人仍可有条件批准本次 ResourceVersion 引用记录，但决定必须明示外部内容未被固定，任何展示不得声称该内容已不可变或可复现。
- 重新审核、更正或撤回通过追加新记录表达，不覆盖历史。同一 ResourceVersion 的当前资格由最近一项有效审核决定确定：后续批准可以恢复资格，后续撤回立即阻止新正式化；已正式化引用的处理遵循下条撤回规则。
- 资源审核人可以追加撤回先前批准的决定。撤回不追溯撤销已正式化的 WikiRevision，不改写其精确引用或 Formal Revision 指针；但该版本从撤回生效后不再满足新的正式化校验。需要修订既有内容时，提交新的 WikiRevision 并引用其他已批准版本。资源资格的当前状态可作为正式查询中的状态提示，历史审核记录保留。
- Wiki Curator 或文档负责人另行审核 Wiki Submission 中的文档内容及其引用是否合适。文档/引用审核和资源资格审核是两项独立决定：通过其中一项不能代替另一项。
- 同一人只有在同时具备相应资源审核授权和 Wiki 审核职责时，才可兼任；必须分别作出并记录两项可独立审计的决定。ResourceVersion 未获批准或仍待审核时，不得因 Wiki 文档审核通过而取得正式引用资格。
- 此分工不替代既有 Project Owner Formal Publication Review。

### 已确认：候选引用与正式引用资格分开

- Wiki 候选版本可以暂时包含指向精确 ResourceVersion ID 的引用，即使该资源版本仍待资源审核；候选内容必须显式显示其资源资格状态，不得将其呈现为已批准资源。
- ResourceVersion 的资源资格审核可以独立于 Wiki Submission 的接纳审核进行。候选可继续在隔离的 Proposal/candidate 中准备，但待审或被拒的 ResourceVersion 会阻止相关 WikiRevision 正式化。
- Wiki Formal Publication Review 前，正式化校验必须确认每个目标 ResourceVersion 已通过单独的资源审核，且批准记录绑定到引用所指的同一不可变版本。Wiki 文档审核或 Project Owner 的正式发布批准均不能替代这项资源审核。
- 被拒绝的 ResourceVersion 不具备正式引用资格；需取得针对同一版本的新批准，或在资源内容变化时创建并审核新的 ResourceVersion。新版本不继承旧版本的审核结论。

### 已确认：Wiki 跨存储正式化边界

- 正式化前置条件为：锁定所审 candidate head；Project Owner 已对固定基准和完整候选方案作出正式发布批准并留下审计决定；当前 Formal WikiRevision 仍等于候选的 `base_formal_revision_id`；候选中的每个 ResourceVersion 均具有当前有效的资源批准。
- 正式化先将锁定的候选精确版本写入 Wiki TerminusDB，并读回确认内容和 Commit 身份；只有该存储结果确认后，才允许执行 SQLite 激活。
- SQLite 的单一本地原子激活单元负责登记 Formal WikiRevision、条件切换文档的当前正式版本指针并写入正式化成功记录。该单元成功提交是 Wiki 正式版本唯一的业务生效边界；Project Owner 批准本身不构成正式化成功。
- 正式查询依据 SQLite 中已激活的正式版本和成功记录确定可见版本，并读取其精确关联的 TerminusDB Commit 作为正文及图内容来源。两侧记录不匹配或该 Commit 不可读时，查询返回不可用/需对账，不回退到其他版本、不静默读取候选。
- 若正式基准在校验后、SQLite 激活前已前进，条件激活必须失败；旧候选不得覆盖新正式版本。阻止该操作正式化，并要求从最新 Formal WikiRevision 建立新的 Submission/Proposal 和候选，再经过相应审核。

### 已确认：正式化失败恢复与幂等

- 每个正式化操作使用稳定的 `formalization_operation_id`；每次尝试保留独立结果记录和递增 `attempt_number`。逻辑状态采用 `requested`、`in_progress`、`store_ready`、`reconciliation_required`、`succeeded`、`failed`：`store_ready` 表示精确 TerminusDB Commit 已读回确认但 SQLite 尚未激活；只有 SQLite 激活单元提交后才记为 `succeeded`。每次重试增加尝试序号但沿用操作标识和原候选输入；候选 head、批准决定或基准版本变化时必须创建新操作。重复请求识别为原操作，不创建重复 Formal WikiRevision。
- TerminusDB 写入返回结果不确定时，先按操作身份、锁定 candidate head 和可用存储证据读回确认。若精确 Commit 已存在且匹配则复用；若可确认未写入，才允许使用同一操作重试；若无法证明写入与否，操作进入待对账，不盲目重写或激活。
- TerminusDB Commit 已成功写入并读回确认、但 SQLite 激活失败时，候选 Commit 保留为不可查询历史；重试必须复用该操作、锁定的候选 head 和已确认的精确 Commit，不重复创建内容版本。
- SQLite 激活提交结果未知时，操作进入显式的待对账状态。先读取 SQLite 的 Formal WikiRevision、当前指针及成功记录，判断激活是否已提交；结果未查明前不得盲目重试激活或创建新 Commit。
- 正式化不执行 TerminusDB 与 SQLite 之间的跨存储回滚。未激活 Commit 永不进入正式查询；对账、人工恢复、指针修正或操作终止都必须追加审计事件，保留原尝试和结果。

### 已确认：通知不属于正式化成功条件

- FormalizationResult 成功且 SQLite 激活提交后，通知投递失败不撤销或延迟正式版本生效。
- 通知作为独立治理记录跟踪投递状态、失败信息和后续重试；通知结果不能改写正式化结果。审核决定、激活结果和恢复动作均追加审计记录。

## Acceptance Criteria

- [x] 定义 ResourceVersion 的正式引用资格条件，指出审核决定者/授权依据、证据字段/对象、审核与精确 ResourceVersion 的绑定方式、拒绝/待审时的引用行为及审计要求。
- [x] 明确 Wiki 正式化的候选锁定、审核批准、各持久化写入及读回确认的顺序和唯一业务生效边界。
- [x] 覆盖每个跨存储部分失败及结果未知状态、幂等重试、对账/人工恢复、通知失败和审计追加规则。
- [x] 明确正式查询权威；两侧不匹配或版本不可读时如何响应，确保候选/未批准/未完成版本不进入正式查询。
- [x] 规格与 ai4-l3sj、ai4-hkdz、ai4-56iu、ai4-zewm、ai4-3nru 的既有决策一致；不将 Mapping 专属 ai4-azx2 当作 Wiki 规则的替代。
- [x] 不规定具体 API、代码实现或未确认的 SDK/外部运行依赖；如需新增依赖，另立依赖任务并完整记录来源、用途、版本、许可证/限制和验证命令。

## Progress

2026-10-20：按用户确认的分开审核方向，完成资源资格审核、候选待审/正式化门槛、审核记录、撤回、跨存储成功边界、幂等与失败恢复、正式查询和通知语义。书面设计见 [`2026-10-20-wiki-resource-review-cross-storage-formalization-design.md`](../docs/superpowers/specs/2026-10-20-wiki-resource-review-cross-storage-formalization-design.md)。规格无新增运行时依赖；当前工单保留 open，供用户检查书面设计。

## Notes

**2026-10-20T13:33:37Z**

2026-10-20 设计复核：已修正正式化顺序中资源资格检查与 Project Owner 审核先后次序的表述矛盾，现明确先核验当前有效且范围适配的资源批准，再进行 Project Owner Formal Publication Review，并在 SQLite 激活时再次校验。既有审核分工、跨存储边界和失败恢复结论不变。资源资格审核已拆分为 ai4-vczt；正式查询、候选提交、审阅/正式化工单已补充相应集成条件和依赖。规格及验收项复核完成。
