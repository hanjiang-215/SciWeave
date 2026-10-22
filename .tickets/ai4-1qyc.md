---
id: ai4-1qyc
status: closed
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

严格实现 ai4-azx2 已关闭的跨存储正式化规格：精确 TerminusDB Commit 写入并读回确认后，SQLite 单一激活单元创建 Formal MappingRevision、条件切换当前指针、写入成功结果并收敛治理状态；SQLite 激活提交是唯一生效点。不执行跨存储回滚，未激活 Commit 保留为不可查询历史。适用规格：`docs/superpowers/specs/2026-10-19-research-mapping-cross-storage-formalization-consistency-and-recovery-design.md`；关联已关闭的 `ai4-mjku`、`ai4-9hcj`。

## Implementation Contract

- **代码位置与入口：** 在 `sci-weave/research-mapping/src/research_mapping/formalization.py` 实现 `MappingFormalizationService.formalize(merge_request_id, operation_id)` 和同一服务的受控恢复/对账入口；授权 Project Owner 的明确批准是必要输入，不实现网络 API。
- **预检：** 校验 MR 锁定的完整方案、候选 head、base Formal MappingRevision、Owner 批准事件和状态；当前正式指针必须仍等于该基准。任何候选或正式基准变化均阻断旧请求，不得静默重放。
- **跨存储顺序：** 使用稳定 `formalization_operation_id`，每次尝试追加 `result_id` 并递增 `attempt_number`。先调用 `TerminusStore.create_formal_snapshot(locked_candidate_ref, operation_id)` 写入/确认精确正式 Commit，再用 `read_exact_snapshot(...)` 读回核对 store/branch/hash/内容摘要；之后才以单一 SQLite 事务创建 Formal MappingRevision、按基准条件更新 `current_formal_revision_id`、将结果置为 `succeeded`，并同步规格要求的来源处置/治理状态。SQLite 激活事务提交是唯一生效点。
- **状态和恢复：** 实现规格状态 `requested`、`in_progress`、`graph_ready`、`reconciliation_required`、`succeeded`、`failed`。已确认图 Commit 但 SQLite 未激活时为 `graph_ready`；任何结果未知或双侧证据不一致进入 `reconciliation_required`。只有未产生可激活 Commit 的确定性失败才记为本次 `failed`。对账按同一操作和精确 Commit 读回；禁止跨存储盲目回滚、重复创建正式版本或在证据不足时报告成功。
- **通知与审计：** 成功激活后再投递通知；通知失败只更新通知投递状态并追加 AuditEvent，不回滚当前指针。对账、修复和人工处置均追加审计记录。
- **验证：** 新增/完善 `tests/test_formalization.py` 和 TerminusDB 集成用例，覆盖 Owner 驳回/越权、基准过期、成功、明确图写入失败、SQLite 激活回滚、SQLite 提交结果未知、Commit 已确认但激活未确认、恢复幂等和通知失败。使用临时 SQLite、Fake TerminusStore 与仓库服务；依赖/环境约定引用 Mapping 地图。

## Acceptance Criteria

- [x] 未授权批准、未锁定候选、基准已过期、候选冲突或审核证据不完整均不能正式化。
- [x] 精确图 Commit 已读回确认后，Formal MappingRevision、条件更新后的当前指针、成功 FormalizationResult 及规格要求的来源处置在同一 SQLite 激活事务中提交；提交前 Formal Query 仍只见旧版本。
- [x] 状态只使用规格规定的六种状态，并满足 `requested → in_progress → graph_ready → succeeded` 正常路径及失败/未知结果分流。
- [x] 同一操作重试沿用 `formalization_operation_id` 和精确 Commit，只递增尝试号，不生成重复 Formal MappingRevision；基准、候选头、审批或选定方案改变时使用新操作身份。
- [x] SQLite 激活确定失败时事务无部分生效；提交结果未知或双侧不一致时进入 `reconciliation_required`，读回核对前不报告成功、不盲目重写。
- [x] 通知失败不撤销成功版本；对账、修复及人工决定保留追加审计证据。
- [x] 自动化/集成验证覆盖成功、驳回、过期、存储失败、SQLite 回滚和未知结果恢复；README 命令及实际结果回写本票。

## Notes

- 2026-10-22：当前身份核对通过：本票 assignee 为 `hanjiang`，当前分支为 `feature/hanjiang`，`git config user.name` 为 `hanjiang`。
- 2026-10-22：恢复边界复查发现，较早的 Owner 批准会在之后已有拒绝/退回事件时仍被选中并允许正式化。新增回归测试先复现该问题，再将资格判断改为“最新审阅事件必须是由 Project Owner 作出的批准”；定向正式化测试通过。
- 2026-10-22：重复调用已成功操作时，现在检查 SQLite 当前指针、正式版本、成功结果的存储/Commit 关联，并精确读回 TerminusDB 快照及摘要；任一证据不一致即返回 `reconciliation_required`，不再仅凭先前 attempt 状态报告成功。
- 2026-10-22：验证命令 `uv run --locked python -m compileall -q src tests` 成功；`uv run --locked python -m unittest discover -s tests -v` 共 67 项，65 项通过、2 项跳过。跳过的是依赖 `SCIWEAVE_MAPPING_INTEGRATION_COMMIT`（及可选 head Commit）的历史 Commit 对比测试；候选分支创建/重放和未知 Commit 集成用例均运行通过。首轮约定命令 `uv run --env-file .env ...` 因本地未提供 `.env` 无法运行，因此改用仓库已锁定依赖的 `uv run --locked`，未创建或填入环境文件。
- 2026-10-22：另外补上 SQLite `commit()` 抛错后可能实际已提交的判定：错误分支先比对指针、正式版本、成功结果、attempt 及精确 TerminusDB 内容；所有证据吻合时才返回成功，否则保持 `reconciliation_required`。这处理了之前失败分支可能把已持久化 attempt 改成对账状态的风险。随后全量验证重新运行：编译成功，67 项测试中 65 项通过、2 项按历史 Commit 配置缺失跳过。
- 2026-10-22：随后将候选 branch head 读取不可用、TerminusDB 正式快照写入抛错和精确读回抛错统一按结果未知处理，避免把服务故障误记为确定性失败；补充候选 head 不可用时必须进入对账的测试。最新全量验证：`uv run --locked python -m compileall -q src tests` 成功；`uv run --locked python -m unittest discover -s tests -v` 共 68 项，66 项通过、2 项因未提供历史 Commit 配置而跳过。
- 2026-10-22：正式化全量验证记录已同步到 README，并新增 `reconcile()` 在未知快照结果后沿用原操作恢复的定向测试。最新全量验证：源码编译成功；69 项测试中 67 项通过、2 项因未提供历史 Commit 配置而跳过；`git diff --check` 无差异格式错误。
- 仍有完成阻塞：完整 SQLite 激活服务与真实 TerminusDB 的端到端联合链路尚未实际验证。真实服务已验证候选分支创建/重放、精确读回、同一精确 Commit 的正式快照引用及未知 Commit 检查；完整历史 Commit 对比需配置对应 Commit。保持本票 `in_progress`，不勾选未实证验收项。
- 2026-10-22：新增 SQLite `commit()` 在激活事务实际持久化后抛出异常的回归测试。首次定向执行发现注入点过早（打断 attempt 建立事务），据此将注入精确限定在成功激活结果已持久化的事务；定向测试通过，并验证当前正式指针、唯一正式版本和成功结果均已持久化后服务返回成功。最新全量验证：编译成功；70 项测试中 68 项通过、2 项因未配置历史 Commit 而跳过；`git diff --check` 通过。真实 TerminusDB 集成验证 4 项中 2 项通过、2 项因未提供历史 Commit 配置跳过。验证记录已同步至 Mapping README。
- 2026-10-22：本轮完成锁定依赖和验收复跑。`uv sync --locked` 成功；`uv run --locked python -m compileall -q src tests` 成功；`uv run --locked python -m unittest discover -s tests -v` 共 74 项，72 项通过、2 项因默认未注入历史 Commit 参数而跳过。随后对仓库本地 TerminusDB 12.0.8 服务（临时库 `sciweave_mapping_it`，历史 Commit `wyqlzhb9wpq9mhz1aub53jfdqhdmqtq`，head `mdx0aig891hmbeifqn951mniinu7kfe`）显式运行 `uv run --locked python -m unittest discover -s tests -p 'test_terminus_integration.py' -v`，4 项全部通过，包含历史 Commit 与 branch head 差异核验；另运行 `uv run --locked python -m unittest discover -s tests -p 'test_mapping_service_terminus_integration.py' -v`，真实 TerminusDB + 临时 SQLite 的候选—审阅—Owner 批准—正式化—查询整链 1 项通过。- 2026-10-22：在已记录的 74 项全量测试和 5 项真实 TerminusDB 整链/集成用例通过基础上，本轮重新运行 Mapping 完整测试 74 项全部通过，显式集成测试 5 项全部通过，`git diff --check` 通过。验收证据覆盖当前票所列正式化、SQLite 激活事务、恢复幂等及真实服务整链要求；验收标准据此完成。该票较早的“仍有完成阻塞”记录由本条最新复验结论取代：真实 TerminusDB 联合链路及显式集成已通过，不再构成阻塞。
