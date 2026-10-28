---
name: owner-handle-merge-candidate
description: 处理一条混合候选——它不是你熟的那个人提交的，作者一栏是多个人拼出来的，而他们谁都不能改它。
---

# 处理混合候选

混合候选是 Centre Agent 把几条互不矛盾的候选合成的一条新候选。它是一个**普通候选**：
同样的预审、同样的批准路径、不引入新的 Proposal 状态。特殊之处全在作者身份上。

## 怎么认出它

候选的 `submitter_id` 以 `merged:` 开头：

```
merged:<sha256(sorted 源作者)[:16]>
```

它不是一个人，是一个由源作者集合算出来的稳定标记。同一组源作者合成两次会得到同一个标记，
这正是它可以幂等重放的原因。

来源明细在候选正文的 `change_set.merged_from`（Wiki 侧在 `document_change` 的 provenance）：

```json
"merged_from": [
  {"proposal_id": "prov-a", "submission_id": "sub-a", "submitter_id": "person:alice"},
  {"proposal_id": "prov-b", "submission_id": "sub-b", "submitter_id": "person:bob"}
]
```

## 三条你必须记住的性质

1. **源作者对这条候选没有任何操作权。** 他们不能改、不能推进、不能撤回、也不能批准它。
   所以「让 alice 去改一下她的那部分」在这个语境下没有意义——她改的是**她自己的源候选**，
   那条独立存在于别处。
2. **不得二次混合。** 服务端在源里发现 `merged:` 开头的作者就直接返回
   `nested_merged_candidate`。要改混合结果，路径是：驳回 → 各源作者提新候选 → 再混合一次。
   不允许套娃，是为了任何一个候选的来源集合永远只有一层、一次读完。
3. **混合不等于消除了冲突。** 混合的前提是那几条候选各改各的（分工），不是各改同一处
   （冲突）。真正的冲突合进来，一条候选里会出现两套互相矛盾的说法，而它看起来只是一个候选。

## 你的动作和普通候选一样

```
preview_candidate(proposal_id, base_formal_revision_id, candidate_head)
create_merge_request(preview_id)      → buffer_id
record_review(buffer_id, decision=..., reason=...)
formalize_candidate(buffer_id, operation_id)
```

差别在 `reason` 和通知：

- **`reason` 里必须点明这是混合候选**，以及你批/驳的是哪几条源的合成结果。
  否则事后看审核事件，会以为这是某个人提交的一条普通候选。
- **通知发给源作者全体，不是发给 `merged:` 标记。** 用 `merged_from` 里的
  `submitter_id` 逐个写进 `recipients`。发给那个标记没有人收得到，而且
  `recipient_resolver_unavailable` 会让整条通知不落盘。
- 通知类型仍是 `candidate_revision_requested` / `candidate_rejected`。不要为混合候选造新类型。

## 批准一条混合候选意味着什么

正式版本会同时包含几条源候选的改动，而源候选各自仍然存在、各自可能还在走自己的流程。
这是设计：混合创建的是**新分支**，从不改写源。

你要确认的是：这几条源的合成结果正是你想要的下一步路线。若只是想批准其中一条，
就不该混合——直接批那一条源候选。混合之后再批准一条「其实只想批一半」的候选，
会让正式图一次前进两步，而其中一步没人审过。

## 混合候选该不该驳回

驳回的典型理由：

- 来源不该被合在一起（两条候选属于两条互不相关的路线）；
- 合成后的影响范围没人说得清（`route_impact=changed` 但报告里没有对应的路线分析）；
- 真正的冲突被合进来了（同一个 `logical_id` 出现两套说法）。

驳回之后**不要马上再混合一次**。让源作者先各自出新候选：混合的输入是有问题的，
再混一遍只会得到同样有问题的输出。
