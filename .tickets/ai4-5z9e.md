---
id: ai4-5z9e
status: open
deps: [ai4-he04]
links: [ai4-he04, ai4-eex0, ai4-a2ba, ai4-oz3s]
created: 2026-10-21T12:14:41Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-fv1r
tags: [centre-control, centre-agents, candidate-prereview]
---
# 中央 Agent 候选预审检查项与失败处置

定义中央 Agent 对有候选分支之后做哪些检查，以及每类失败如何处置：格式、对象引用、权限范围、依赖关系、基准版本、冲突和影响范围。

## Design

修订（2026-10-21）：本票原写「对已接纳提交的预审」，把预审对象当作草稿。现改为作用在**候选分支**上：输入是精确 candidate head、base formal revision 和候选内容，不是草稿箱里的草稿。

检查项（2026-10-24 依「候选创建的机械校验前置」ai4-eex0 重排）：格式与结构、对象引用、依赖关系三项已在领域 MCP 写入候选时拒绝，中央 Agent 的输入永远是干净候选，不再出现这三类失败。

| 检查 | 输入 | 判定 |
| --- | --- | --- |
| 权限范围 | 提交者、审核人、目标单元的操作权限 | 越权即失败，不由中央 Agent 补授权 |
| 基准版本 | 候选 `base_formal_revision_id` 是否等于当前正式版本 | 不相等即报告事实 `stale`（`base` 不存在已在写入时拒绝，见 ai4-eex0） |
| 冲突 | 同批可送审候选在同一逻辑对象上的改动 | 冲突即报告事实 `conflict`，须新候选解决 |
| 影响范围 | 从不可调度变可调度、受影响资源引用与执行记录 | 无法说明影响即不得进入送审 |

失败处置映射（2026-10-24 依「中央 Agent 候选预审入口与结论回写」ai4-he04 Resolution 重述）：中央 Agent 不改 Proposal 状态、不写正式版本、不建 Merge Request Buffer；`stale` 与 `conflict` 是预审报告的事实列，Proposal 状态由 Project Owner 在批准或驳回时处置。`abandoned` 仅剩权限失败一类来源。stale/conflict/权限失败都须由提交方生成新的候选，不改写原候选。

约束：

- 预审不写正式版本，也不创建 Merge Request Buffer。
- 预审通过只表示候选可以送 Project Owner 选择，不代表批准。
- 结论经留痕工具落盘，不由中央 Agent 自带私有审计通道。
- 中央 Agent 不审核 Task Agent 设计稿；设计稿的一审是 Project Owner，在草稿箱内完成。

## Acceptance Criteria

- [x] 每项检查有明确输入、判定与稳定失败码（四项检查表已按 2026-10-24 重排，见 Design）
- [x] 每种失败对应确定的 Proposal 状态，且不产生新的正式版本（`stale`/`conflict` 为报告事实列，Proposal 状态由 Project Owner 处置）
- [x] 基准变化或候选 head 变化使既有预审结论失效（追加 `base_moved`/`head_moved` 判定，见 ai4-oz3s）
- [x] 预审不越过 Project Owner 做批准（预审通过仅表示可送审，不是批准）
- [ ] 预审结论经留痕工具记录，重复预审同一对象结论可复现（依赖 `append_prereview_log` 写端，待 ai4-t2wc/ai4-rlv6 收口）

## Notes

**2026-10-21 修订记录**

原题「中央 Agent 预审检查项与失败处置」的正文把预审对象写成「已接纳提交」。按 2026-10-21 讨论，一审在草稿箱、二审初步审核在候选分支，本票改为后者。冲突记录见 `docs/data-flow/draft-buffer.md` 第 8 节。

**2026-10-21T23:45:00Z**

2026-10-21 第五轮讨论的修订。本票挂到「中央 Agent 候选预审职能地图」(ai4-fv1r) 之下。检查表需要按以下结论重排，由本票负责人裁决是否接受：

- **格式、对象引用、依赖关系三项前移到领域 MCP**：在创建候选时就拒绝，不进候选分支。中央 Agent 侧不再有这三类失败，相应地 `abandoned` 只剩权限失败一类。见「候选创建的机械校验前置」(ai4-eex0)。
- **基准版本比对拆分**：「`base` 不存在」在写入时拒绝；「`base` 不等于当前正式版本」仍作为预审判定为 `stale`。
- **纳入范围不按基准过滤**：基准过旧的候选同样纳入预审，`stale` 只是报告里的一列。见「预审门禁、触发范围与故障处置」(ai4-a2ba)。
- **冲突矩阵并入本票的报告格式**：一轮预审拉取同一时点的全量可送审候选做快照，不再逐候选独立判定。
- **判据版本化**：报告须记 `rule_set_version`，只记版本号与检查项清单，不记提示词全文。

**2026-10-24T04:34:57Z**

负责人转交：原负责人为 Frank Qi。2026-10-24 经原负责人确认，与「中央 Agent 候选预审入口与结论回写」(ai4-he04) 一并转交给 hanjiang。原因：检查表仍由入口票挡住，两张票交给同一人收口。本票 deps 仍是 ai4-he04，未解除。正文检查表尚未按 2026-10-21T23:45:00Z 的 Notes 重排：格式、对象引用、依赖三项前移见「候选创建的机械校验前置」(ai4-eex0)；预审结论不改 Proposal 状态，见 he04 的 Resolution。原文保留，由新负责人裁决是否接受。

**2026-10-24 eex0 落地后接受检查表重排（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

裁决：接受 2026-10-21T23:45:00Z Notes 的重排，正文检查表已按此更新，同时按 ai4-he04 Resolution 重述失败处置：

- 格式、对象引用、依赖关系三项从中央 Agent 检查表移除，前移到领域 MCP 写入时拒绝（ai4-eex0 已实现并验收）。
- 基准版本只判「base 是否等于当前正式版本」→ 报告事实 `stale`；`base` 不存在已在写入时以 `base_revision_missing` 拒绝。
- `stale`/`conflict` 改为预审报告事实列，中央 Agent 不改 Proposal 状态；`abandoned` 只剩权限失败一类。
- 保留的检查：权限范围、基准版本、冲突、影响范围。

本票仍 open：入口「中央 Agent 候选预审入口与结论回写」(ai4-he04) 的领域管理 MCP 只读候选查询与 `append_prereview_log` 尚未闭环，检查表的重排生效依赖它。验收勾选待 he04 收口后复验。
