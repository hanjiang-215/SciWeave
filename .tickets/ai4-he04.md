---
id: ai4-he04
status: open
deps: [ai4-upsm]
links: [ai4-upsm, ai4-5z9e, ai4-oz3s, ai4-eex0]
created: 2026-10-21T12:14:32Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-fv1r
tags: [centre-control, centre-agents, candidate-prereview]
---
# 中央 Agent 候选预审入口与结论回写

中央 Agent 从 Research Mapping 与 LLM-Wiki 的管理 MCP 读取**已存在的候选分支**，生成预审材料，并把结论写回该候选的治理记录。草稿箱不参与这条链路。

## Design

修订（2026-10-21）：本票原为「Buffer 取件与预审结论回写」，假设中央 Agent 读草稿箱里已接纳的提交。讨论结论是草稿一审由人完成、通过后由人调用领域管理 MCP 写入候选分支，中央 Agent 的工作从候选存在那一刻开始，因此入口从草稿箱改为领域管理 MCP 的候选读取。原表述见下方 Notes 的修订记录。

已定边界：

- 中央 Agent 对中央草稿箱只读或不读，绝不写草稿的 `accepted`/`rejected`。
- 一审由命名空间配置的审核人完成；转成候选由人调用领域管理 MCP 完成，不是中央 Agent 代劳。
- 中央 Agent 只处理候选：读取精确 candidate head、base formal revision 与候选内容，产出预审材料并回写结论。
- 结论写回领域治理记录（不是草稿箱），并经留痕工具追加审计。

待定（已于 2026-10-22 全部定案，见下方「## Resolution」）：

- 预审入口形态：由领域管理 MCP 新增只读候选查询工具，还是中央 Agent 直接用现有 Store 接口。
- 取件是否带租约以避免两个中央 Agent 实例重复预审同一候选。
- 预审结论的状态取值与它和 Proposal 状态（`candidate`、`mr_ready`、`stale`、`conflict`）的对应关系。
- 中央 Agent 能否为「需要混合」的候选写新候选分支；若可以，它的写入位置与作者身份如何记录。

## Resolution

**入口：只走领域管理 MCP 的只读候选查询工具。** 两套管理 MCP 各提供一个只读工具，返回同一时点的全部可送审候选（未放弃、未正式化、未驳回）及其精确 `candidate_head`、`base_formal_revision_id` 与内容快照。Centre Agent 不持有领域 Store 的连接，不直连领域数据库。

理由：Centre Agent 与领域治理之间只应有进程边界这一条通道。直连 Store 会让领域 schema 的每次变更都变成 Centre Agent 的破坏性变更，也会让「谁能读候选」这件事绕开 MCP 的授权面。查询是只读的，故不需要第二个写工具。

**取件不带租约。** 单实例常驻，重复预审由「预审报告的追加日志契约」(ai4-oz3s) 的唯一键 `(candidate_id, candidate_head, rule_set_version)` 挡住，返回首次结论。本地 Worker Lease（见「最小 Work Agent 实现规格」ai4-z3z4）只用于同一 `candidate_id` 不并发跑两轮，不承担跨实例分发。

**结论状态取值：不提交通用 Proposal 状态，只提交本报告的事实列。** 报告带 `verdict`（通过/不通过）与 `conflict_matrix`；`stale`（基准过期）与 `conflict`（同对象冲突）是报告里的事实，不是 Centre Agent 写入的 Proposal 状态。Proposal 状态由 Project Owner 在批准或驳回时处置，Centre Agent 不改 Proposal 状态、不写正式版本、不建 Merge Request Buffer。

**可以为混合候选新建分支，仅此一种写入。** 通过 `create_merged_candidate` 写，与 `append_prereview_log` 是分开授权的两个工具。作者记为全部来源作者，来源作者对该混合候选没有任何操作权，且不可二次混合。细节见「混合候选的生成与作者身份」(ai4-8dgd)。

**报告失效与重算。** 候选头变化产生新报告条目，旧条目保留并标 `superseded_by`；正式版本发布时，受影响候选的旧报告标 `stale` 并在下一次预审时重算，重算完成前该候选卡住。见「预审门禁、触发范围与故障处置」(ai4-a2ba) 与 `docs/data-flow/centre-agent.md`。

## Acceptance Criteria

- 只能读到已存在的候选分支；草稿箱内容不进入预审输入
- 不写草稿的接纳或驳回状态
- 入口为领域管理 MCP 的只读候选查询工具，不直连领域 Store
- 同一候选 head 不会被并发预审两次，或被重复预审时结论一致
- 预审结论写回领域治理记录并留痕，不写正式版本，不改 Proposal 状态
- 只能通过 `create_merged_candidate` 新建混合候选分支，不改写已有候选
- 候选 head 或 base formal revision 变化后，旧预审结论失效且有明确标记
- 有回归测试覆盖重复取件、并发取件与预审对象变化

## Notes

**2026-10-21 修订记录**

原题「Buffer 取件与预审结论回写」，原 Design 为「中央 Agent 从 Buffer 取出『领域审核人已接纳』的提交」。该前提已被 2026-10-21 讨论推翻：草稿的一审是人，转候选是人调用 MCP，中央 Agent 审的是候选。冲突记录见 `docs/data-flow/draft-buffer.md` 第 8 节。

**2026-10-21T23:45:00Z**

2026-10-21 第五轮讨论的修订。本票挂到「中央 Agent 候选预审职能地图」(ai4-fv1r) 之下，并受以下决定约束：

- **结论存储形态已定**：以只追加日志写入领域治理记录，唯一键为 `(candidate_id, candidate_head, rule_set_version)`。详见「预审报告的追加日志契约」(ai4-oz3s)。本票 Design 的「待定」中「预审结论的状态取值」由该票承接。
- **分发租约不再需要**：中央 Agent 单实例常驻，恢复靠报告唯一键幂等。本票 Design 的「待定」中「取件是否带租约」一项作废。
- **入口形态不再待定**：领域管理 MCP 新增只读候选查询工具，中央 Agent 不经 Store 接口直连。
- **写新候选分支确认为可以**：仅限混合候选，作者记为全部来源作者且来源作者无操作权，见「混合候选的生成与作者身份」(ai4-8dgd)。

机械校验前移后，本票与「候选预审检查项」(ai4-5z9e) 的输入不再包含格式非法的候选，见「候选创建的机械校验前置」(ai4-eex0)。

**2026-10-22T09:15:00Z**

2026-10-22：四个待定项全部定案，写入正文 `## Resolution`。依据 Project Owner 裁决与 `docs/data-flow/work-agent.md`。同时新增两条验收：入口不直连领域 Store、只可新建混合候选分支不改写已有候选。

阻塞状态：本票 `deps` 为 `ai4-upsm`（中央服务留痕工具），该票已关闭，本票不再受阻。

> 更正（2026-10-22T14:10:00Z）：上一条写于 2026-10-22 09:15 的说明已过期并保留原文。留痕工具的语义已改为「接口层对外调用账本」，包位置改为 `sci-weave/centre-control/shared/audit-trail`，`ai4-upsm` 已关闭。详见 [中央留痕工具共享包实现规格](ai4-tg3v.md) 与其代码落地票 [留痕包迁移到 centre-control 并改造为接口层调用账本](ai4-gvan.md)。本票的「留痕」指的是预审结论经领域管理 MCP 落库时的对外调用记录，不再要求领域代码在写事实的同一事务里调 `write_audit_event`。
