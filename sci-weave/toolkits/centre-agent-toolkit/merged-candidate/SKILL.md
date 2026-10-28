---
name: centre-merged-candidate
description: 把几条互不矛盾的候选合成一条新候选分支，并守住「只新建、不改源、不再混」三条线。
---

# 混合候选

混合候选是**一条普通候选**：它走同一套预审、同一个 Project Owner 批准路径，不引入新的
Proposal 状态。它唯一特殊的地方是来源不止一个。

## 什么时候才该混合

混合解决的是**分工**，不是冲突：

- 候选 A 改了 `TaskNode/logical-3`，候选 B 改了 `TaskNode/logical-8`，两条都单独可送审；
  把它们合成一条能让 Project Owner 一次看到完整的一步推进。——该混合。
- 候选 A 与候选 B 都改 `TaskNode/logical-3` 且版本不同。——这是**冲突**，不是分工。
  混合会把两个互相矛盾的版本塞进一个分支，让一条候选里出现两套说法。该由提交方出新候选，
  或由 Project Owner 选一条。

判断依据是 `conflict-matrix` 的结果：`conflict_matrix` 里出现同一 `logical_id`
就不该混合。不要在混合之后再让人去发现冲突。

## 三条硬约束

```
create_merged_candidate(
  mapping_domain_id="...",
  source_proposal_ids=["prov-a", "prov-b"],
  base_formal_revision_id="...",
  change_set={...},
  idempotency_key="merge-<digest>",
)
```

1. **只新建。** 源候选永不被编辑。混合产生一条新分支，源候选原样留在那里。
2. **作者是多值的。** 服务端把 `submitter_id` 写成 `merged:<hash(sorted 源作者)>`，
   并把每个源的 `proposal_id`/`submission_id`/`submitter_id` 写进 `change_set.merged_from`，
   digest 因此覆盖了来源。**源作者对这条混合候选没有任何操作权**——他们不能改它、
   不能替代它，也不能用它去覆盖自己的源候选。
3. **不得二次混合。** 源候选的作者以 `merged:` 开头时直接返回 `nested_merged_candidate`。
   混合一条已经混合过的候选，等于把 provenance 压成一层，之后没人能追出原始作者。

## 其他服务端拒绝

| 返回 | 原因 |
| --- | --- |
| `source_candidate_not_found` | `proposal_id` 不属于这个 `mapping_domain_id` |
| `source_candidate_not_reviewable` | 源候选状态不是 `candidate` / `review_pending` / `approved_pending_formalization` |
| `nested_merged_candidate` | 源里已经有混合候选 |
| `invalid_change_set` / `invalid_task_node` | 合成后的正文没过机械校验 |

源候选必须都在**同一个正式基座**上——`base_formal_revision_id` 是单一值。跨基座的候选
不能混合：它们的差异里已经混进了两个正式版本之间的变化，合成后就说不清哪部分是候选带来的。

## 混合之后

混合候选和别的候选一样要预审、要等 Project Owner 决定。你要做的是：

1. 对这条新候选跑一遍预审（`prereview-checks`）；
2. 报告里点明它来自哪几条源候选，让 Project Owner 知道这不是某个研究员提的；
3. 通知用 `prereview_completed`，不要另造一种通知类型。

## 你不能做的

- 混合之后自己批准它（`formalize_candidate` 不在你能调的范围里）。
- 通过「先混合再删源」的方式绕过冲突——源候选删不掉，只能被驳回。
- 一次调用同时改 Mapping 与 Wiki。两个域各混各的，各写各的报告。
