---
id: ai4-z0lb
status: open
deps: [ai4-6s53]
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-6ljq
tags: [mapping, implementation]
---
# Mapping 候选差异与审阅纵向实现

实现 Research Mapping 候选审阅路径：针对固定的正式基线和不可变候选生成结构化差异与影响预览，支持将一份固定候选提交为 Merge Request Buffer，并记录预审/审阅结果，供正式负责人作出最终批准或驳回决定。

## Design

差异与影响范围围绕 TaskNode、DependencyEdge、输入输出及路线激活条件。审阅对象必须绑定明确的 base Formal MappingRevision 和 candidate head；基准变化或候选 head 变化时重新验证并使旧预览失效。最终正式化成功条件仍由独立的正式化任务实现。适用规格：已关闭的 Proposal 生命周期 `ai4-xrxw`、候选治理记录 `ai4-mjku`、草稿/正式视图 `ai4-u3rs` 和候选分支验证 `ai4-2alw`；`docs/superpowers/specs/2026-10-19-research-mapping-candidate-governance-record-model-design.md`。

## Implementation Contract

- **代码位置与接口：** 在 `sci-weave/research-mapping/src/research_mapping/review.py` 实现 `MappingReviewService.preview(proposal_id, base_formal_revision_id, candidate_head)` 及固定候选头创建 Merge Request Buffer 的应用服务；沿用前置子票建立的 SQLiteStore 和 TerminusStore。
- **审阅快照：** `TerminusStore.read_exact_snapshot(...)` 按精确 Formal MappingRevision 的 commit ref 与 candidate head commit hash 读取两个不可变快照。预览输入绑定精确 Proposal、正式基准版本和 candidate head；输出包含稳定 preview/evidence ID、TaskNode/DependencyEdge 字段差异、受影响对象及路线影响摘要；证据写入 SQLite，候选正文仍只存在 TerminusDB。Buffer 固定引用预览和候选头，不复制正文。
- **失效和拒绝：** 基准已前进、candidate head 改变、Proposal/Commit 不匹配、Commit 不可读或差异证据不完整时，不得产生可批准的有效 Buffer；返回明确的 `stale_base`、`candidate_mismatch`、`candidate_unavailable` 或 `preview_unavailable` 结果，并保留可审计原因。旧 preview 不得被覆盖成新候选的证据。
- **审核边界：** 记录预审/审阅的操作者、时间、决定与理由；最终 Project Owner 正式批准仍由 `ai4-1qyc` 实施，Agent 不可自行批准或触发正式化。
- **验证：** 新增 `tests/test_review.py`，使用临时 SQLite/Fake TerminusStore 覆盖无变更、有效差异、重复读取一致、基准前进、head 改变、候选不可读、Buffer 固定头及审核记录；使用 Mapping 地图中的测试命令和环境变量，不引入新测试依赖。

## Acceptance Criteria

- [ ] 对精确基准和 candidate head 生成可重复读取的结构差异、受影响对象和路线影响证据。
- [ ] Merge Request Buffer 固定引用 Proposal、候选 head、基准正式版本、预览结果及提交/审阅记录；候选正文不复制、不原地修改。
- [ ] 基准已前进、候选 head 不匹配、候选不可读或预览不完整时返回明确失败结果，不创建可批准的有效请求，且旧证据不被覆盖。
- [ ] 通过、退回或拒绝等预审/审阅决定保留操作者、UTC 时间、理由及审计关联；最终批准仅由后续 Owner 流程完成。
- [ ] `tests/test_review.py` 覆盖无变更、有效差异、基准过期、head 失配、候选不可读和 Buffer 锁定；标准库验证命令及输出证据随实现回写。
