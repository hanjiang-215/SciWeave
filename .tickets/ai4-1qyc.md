---
id: ai4-1qyc
status: open
deps: [ai4-z0lb]
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-6ljq
tags: [mapping, implementation]
---
# Mapping 正式化与失败恢复纵向实现

实现 Mapping Project Owner 对固定 Merge Request Buffer 的批准/驳回与正式化路径，并覆盖 TerminusDB Commit 已确认但 SQLite 激活失败或结果未知时的幂等重试、读回对账和恢复。

## Design

严格实现 ai4-azx2 已关闭的跨存储正式化规格：精确 TerminusDB Commit 写入并读回确认后，SQLite 单一激活单元创建 Formal MappingRevision、条件切换当前指针、写入成功结果并收敛治理状态；SQLite 激活提交是唯一生效点。不执行跨存储回滚，未激活 Commit 保留为不可查询历史。

## Implementation Contract

- **代码位置与入口：** 在 `sci-weave/research-mapping/src/research_mapping/formalization.py` 实现 `MappingFormalizationService.formalize(merge_request_id, operation_id)` 和同一服务的受控恢复/对账入口；授权 Project Owner 的明确批准是必要输入，不实现网络 API。
- **预检：** 校验 MR 锁定的完整方案、候选 head、base Formal MappingRevision、Owner 批准事件和状态；当前正式指针必须仍等于该基准。任何候选或正式基准变化均阻断旧请求，不得静默重放。
- **跨存储顺序：** 使用稳定 `formalization_operation_id`，每次尝试追加 `result_id` 并递增 `attempt_number`。先调用 `TerminusStore.create_formal_snapshot(locked_candidate_ref, operation_id)` 写入/确认精确正式 Commit，再用 `read_exact_snapshot(...)` 读回核对 store/branch/hash/内容摘要；之后才以单一 SQLite 事务创建 Formal MappingRevision、按基准条件更新 `current_formal_revision_id`、将结果置为 `succeeded`，并同步规格要求的来源处置/治理状态。SQLite 激活事务提交是唯一生效点。
- **状态和恢复：** 实现规格状态 `requested`、`in_progress`、`graph_ready`、`reconciliation_required`、`succeeded`、`failed`。已确认图 Commit 但 SQLite 未激活时为 `graph_ready`；任何结果未知或双侧证据不一致进入 `reconciliation_required`。只有未产生可激活 Commit 的确定性失败才记为本次 `failed`。对账按同一操作和精确 Commit 读回；禁止跨存储盲目回滚、重复创建正式版本或在证据不足时报告成功。
- **通知与审计：** 成功激活后再投递通知；通知失败只更新通知投递状态并追加 AuditEvent，不回滚当前指针。对账、修复和人工处置均追加审计记录。
- **验证：** 新增/完善 `tests/test_formalization.py` 和 TerminusDB 集成用例，覆盖 Owner 驳回/越权、基准过期、成功、明确图写入失败、SQLite 激活回滚、SQLite 提交结果未知、Commit 已确认但激活未确认、恢复幂等和通知失败。使用临时 SQLite、Fake TerminusStore 与仓库服务；依赖/环境约定引用 Mapping 地图。

## Acceptance Criteria

- [ ] 未授权批准、未锁定候选、基准已过期、候选冲突或审核证据不完整均不能正式化。
- [ ] 精确图 Commit 已读回确认后，Formal MappingRevision、条件更新后的当前指针、成功 FormalizationResult 及规格要求的来源处置在同一 SQLite 激活事务中提交；提交前 Formal Query 仍只见旧版本。
- [ ] 状态只使用规格规定的六种状态，并满足 `requested → in_progress → graph_ready → succeeded` 正常路径及失败/未知结果分流。
- [ ] 同一操作重试沿用 `formalization_operation_id` 和精确 Commit，只递增尝试号，不生成重复 Formal MappingRevision；基准、候选头、审批或选定方案改变时使用新操作身份。
- [ ] SQLite 激活确定失败时事务无部分生效；提交结果未知或双侧不一致时进入 `reconciliation_required`，读回核对前不报告成功、不盲目重写。
- [ ] 通知失败不撤销成功版本；对账、修复及人工决定保留追加审计证据。
- [ ] 自动化/集成验证覆盖成功、驳回、过期、存储失败、SQLite 回滚和未知结果恢复；README 命令及实际结果回写本票。
