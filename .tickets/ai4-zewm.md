---
id: ai4-zewm
status: closed
deps: [ai4-36ek, ai4-2sdn]
links: []
created: 2026-10-17T03:22:08Z
type: grilling
priority: 1
assignee: hanjiang
parent: ai4-ru15  # 动态科研协作平台需求地图
tags: [wayfinder:grilling, wiki, proposal, terminusdb, ai4science]
---
# Wiki Proposal 与 Merge Request Buffer 生命周期

## Question
统一 LLM-Wiki 中 Wiki Buffer Submission、Wiki Proposal、candidate branch、candidate Commit、Merge Request Buffer、Formal WikiRevision 的生命周期和状态转换。需要明确第一阶段接纳审核后如何创建 Proposal 与候选分支；候选 Commit 何时锁定为只读；Agent 如何通过 MCP 提交 Merge Request Buffer；无冲突、冲突、多方案选择、Project Owner 通过、驳回、未选中和返修分别如何转移状态；哪些对象允许继续写入，哪些只能审计读取。只讨论 LLM-Wiki 内部治理，不涉及 Research Mapping 或具体 API/数据库实现。

## Acceptance Criteria
形成 Wiki 治理对象及其状态清单；明确对象之间的关联和生命周期转换；覆盖正常正式化、并行冲突、多方案选择、部分意见返回、未选中方案和基于新 Formal WikiRevision 返修；明确 candidate Commit 锁定和 Merge Request Buffer 的边界；结论可直接约束后续 Wiki 领域模型和 MCP 工具设计。

## Answer
本轮确定 LLM-Wiki 采用“Buffer 接纳、Proposal 候选、Merge Request Buffer 正式化请求、Formal WikiRevision 正式事实”的生命周期。一个正式版本可以派生多个并行候选分支，候选分支之间允许存在竞争性修改，但候选内容不能直接覆盖其他提交者的原始修改。

### 1. 治理对象和基本关系

```text
Wiki Buffer Submission
  → 第一阶段接纳审核
  → Wiki Proposal
  → candidate branch
  → candidate Commit / candidate WikiRevision
  → Merge Request Buffer
  → Project Owner 选择或审核
  → Formal WikiRevision
```

- `Wiki Buffer Submission` 是端侧 Agent 的外部提交入口，承载单个文档变更单元及其资源引用关系。
- 第一阶段由任务产出对应的审核人接纳或退回。通过后才创建或加入 Wiki Proposal，并写入该 Proposal 的 candidate branch；Project Owner 阶段不再返回普通 Wiki Buffer。
- 一个 Wiki Proposal 使用自己的 candidate branch，可以从同一个 Formal WikiRevision 派生多个并行 Proposal/candidate branch。Proposal 的治理状态保存在 Wiki 平台，不依赖 TerminusDB branch 元数据。
- `candidate Commit` 是 TerminusDB 中的不可变候选存储版本；它记录候选内容，但不代表已获得正式批准。
- Agent 通过 Wiki MCP 创建 `Merge Request Buffer`，请求将某个固定 candidate head 正式化。Merge Request Buffer 不重复承载 Wiki 正文，而是引用 Proposal、candidate branch、candidate head、base Formal WikiRevision、dry-run 结果和审查信息。
- Project Owner 的正式审核以整个 Merge Request Buffer 或其中一个完整方案为单位；不在正式化阶段拆分并部分推进同一个候选方案。

### 2. Candidate branch 和 candidate Commit 的可写边界

- Candidate branch 在准备草稿期间可以产生多个 Commit。
- Agent 提交 Merge Request Buffer 时，平台锁定当时的 `candidate head`，该 head 及其祖先 Commit 成为本次正式化请求的固定审查对象。
- 被 Merge Request Buffer 引用的 candidate head、candidate Commit 和 Diff 只能读取，不能继续追加写入或原地修改。
- 未提交 Merge Request 的活动候选分支可以继续产生新的候选 Commit，但每次新的正式化请求都必须重新固定一个 candidate head。
- 被拒绝、未选中或已完成的 candidate branch 默认保留为只读审计对象；平台通过 Proposal 状态和写入权限阻止继续写入。TerminusDB 的物理删除不表示业务上的废弃，第一阶段不依赖删除完成归档。

### 3. 冲突检测和解决

- 在创建 Merge Request Buffer 或提交正式化请求前，Agent 必须调用 Wiki MCP 提供的 `diff` 或 `merge dry-run` 能力。
- 检测范围包括：同一 WikiDocument、同一 Resource Reference、Entity/Concept 关系、共享引用关系，以及 candidate branch 的 base Formal WikiRevision 是否仍是当前有效基准。
- 如果当前 formal branch 已经前进，或多个候选分支修改了相同逻辑对象或关系，Merge Request Buffer 标记为 `conflict`，不能直接正式化。
- 冲突解决 Agent 可以读取相关 Proposal、candidate Commit、Diff 和最新 Formal WikiRevision，生成新的候选解决版本，但不能修改任何其他提交者的 candidate branch 或原始 Commit。
- 冲突解决结果必须是新的不可变 candidate Commit 或新的 candidate branch，并记录它参考的 Proposal、candidate Commit 和解决说明。
- Agent 可以在同一个 Merge Request Buffer 中提供多个完整解决方案，例如采用候选 A、采用候选 B，或生成综合候选 C。每个方案都需要有独立的 Diff、影响范围和冲突处理说明。

### 4. Project Owner 的选择和正式化

- Project Owner 在 Merge Request Buffer 中选择一个完整方案，而不是直接编辑或拼接候选内容。
- 被选中的方案直接进入正式化流程，不需要重新放回普通 Wiki Buffer；平台验证基准、冲突检查和审核记录后，将该候选结果推进到 formal branch，并创建新的 Formal WikiRevision。
- 一个 Merge Request Buffer 最终只能产生一个 Formal WikiRevision。候选 Commit、Proposal 和 Merge Request Buffer 的存储 Commit 不因正式化而被改写。
- Project Owner 可以自行审核，也可以使用平台已有的授权审核安排；平台只记录实际操作、选择、审核意见和通知，不额外建立产品责任归属模型。

### 5. 驳回、未选中和后续返修

- 如果 Project Owner 明确不接受当前方案，Merge Request Buffer 标记为 `rejected`，保留候选内容、Diff 和拒绝理由；对应 candidate branch/head 只读。
- 如果多个方案都可行但最终选择了其中一个，未被选择的方案标记为 `not_selected`，不表示其内容一定错误；对应提交者收到通知。
- 被选方案正式化后，其他提交者可以接受新的 Formal WikiRevision，不再继续修改；也可以基于新的正式版本重新创建 Wiki Buffer Submission，生成新的 Proposal 和 candidate branch。不能继续基于旧 candidate branch 修改。
- Project Owner 选择的是完整候选方案，不在 formal branch 上直接接受其中部分修改。若需要部分保留或重新组合，Agent 应根据意见生成新的完整候选版本，再创建新的 Merge Request Buffer。
- 所有旧 Proposal、candidate Commit、Merge Request Buffer、Diff、选择结果、拒绝理由和通知记录都保留供审计读取；普通查询不读取这些候选对象。

### 6. 生命周期状态

平台至少需要表达以下状态，具体字段名可在后续领域模型中确定：

- Wiki Buffer Submission：`draft`、`submitted`、`accepted`、`rejected`、`revised`；
- Wiki Proposal：`draft`、`candidate`、`merged`、`rejected`、`not_selected`、`abandoned`；
- Merge Request Buffer：`draft`、`submitted`、`conflict`、`approved`、`rejected`、`not_selected`、`merged`；
- Candidate Resolution：`proposed`、`selected`、`not_selected`、`blended`；
- candidate branch/head：活动候选、已锁定、只读归档；
- WikiRevision：`draft` 或 `formal`，具体正式版本通过 Formal WikiRevision 指针确定。

这些状态是 Wiki 平台的治理事实。TerminusDB Commit 只记录存储变化，branch 本身不承担 Proposal 状态、选择结果、拒绝原因或只读归档语义。

最终规则是：普通查询只读取 formal branch 的当前 Formal WikiRevision；审计查询才按 Proposal 读取 candidate branch、candidate Commit、Diff、Merge Request Buffer 和全部治理事件。

### 7. 补充确认：blended 方案和单一选择

- Merge Request Buffer 可以包含多个完整候选方案，但 Project Owner 最终只能选择其中一个方案正式化。
- 候选方案除了直接采用某个 Proposal 的结果，还可以标记为 `blended`：Agent 将多个 Proposal 的修改分析后组合为一个新的完整候选提交。`blended` 表示新候选结果的来源形态，不表示修改了任何原始 Proposal 或 Commit。
- `blended` 方案必须是新的不可变 candidate Commit 或 candidate branch，并记录所有被混合的来源 Proposal、来源 Commit、保留内容、舍弃内容和冲突解决说明。
- 一旦 Project Owner 选择 `blended` 方案，该新候选结果直接正式化；被参考但未被直接采用的原始方案不被覆盖，按实际结果标记为 `not_selected` 或其他适用的治理状态，并通知其提交者。
- Merge Request Buffer 不允许同时选择多个方案，也不允许把多个方案分别部分正式化。

## Review conclusion (2026-10-18)

本票据明确的是后续 LLM-Wiki 治理设计，不是首版 Research Mapping 的交付依赖。它与 `ai4-3nru` 的统一治理语义一致：候选分支状态、只读控制和审计归档由平台结构化记录维护，TerminusDB branch/Commit 只承担存储历史。首版只复用其中的“候选不可变、head 锁定、完整方案单选”原则。
