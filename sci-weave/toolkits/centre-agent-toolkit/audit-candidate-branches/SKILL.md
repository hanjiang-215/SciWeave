---
name: centre-audit-candidate-branches
description: 核对候选分支本身是否真的如它声称的那样——head、基座、来源与快照，而不是先看内容对不对。
---

# 核对候选分支

预审回答「这条候选该不该进正式图」。在那之前有一步更容易被跳过：**这条候选分支是不是真的
就是它声称的那条**。快照读不出来、head 对不上、来源说不清，后面所有判断都建在沙子上。

## 四件事实，按顺序核

```
list_reviewable_candidates(mapping_domain_id)      # 或 list_reviewable_wiki_candidates
```

对每个候选：

1. **`snapshot_status`**。不是 `available` 就没有正文。带 `reason_code` 时会给出
   `candidate_store_unavailable`、`candidate_snapshot_missing`、
   `candidate_snapshot_digest_mismatch` 之类。**没有正文的候选一条结论都不能下**，
   包括「看起来没问题」——那是最危险的一种结论。
2. **`candidate_head`**。这是 SQLite 里记录的精确 commit，领域 MCP 按它去 TerminusDB
   读快照。它和 `candidate_commit_id`、`proposal_id`、`submission_id` 是四个不同的东西，
   汇报时不要混着说。
3. **`base_formal_revision_id`**。与当前正式版本比较，只影响 `stale` 这一列，不影响是否
   纳入本轮。空的基准在 Wiki 侧根本进不来（`formal_base_required`），在 Mapping 侧说明
   该域还没有任何正式版本。
4. **`submitter_id`**。以 `merged:` 开头的是混合候选，来源在 `change_set.merged_from` /
   `document_change` 的 provenance 里。混合候选的「作者」不是一个人，别按单人候选去判权限。

## 为什么要单独做这一步

`candidate_snapshot_digest_mismatch` 这一类只可能在这里被发现：候选创建时摘要算过一次，
预审时按精确 commit 再读一次，两者不一致说明存储里的内容变了。此时**不要**去修候选，
也不要重算摘要——把 `reason_code` 原样写进报告的检查项，让提交方重提。

同样，`prereview_status` 的三个状态（`missing_report` / `report_current` / `report_stale`）
是每轮核对的第一件事：一条 `report_stale` 的候选即使内容看起来完美，也还不该被送去裁决。

## 和「审内容」的分界

| 这一步 | 下一步 |
| --- | --- |
| 这条分支可读吗？head/基座/来源对得上吗？ | 内容对不对？冲突、影响范围、权限 |
| 结论：能读 / 不能读，为什么 | 结论：passed / failed，为什么 |

不能读就不要往下走。把「读不出来」写成一条 `verdict=failed` 的检查项、`reason_code`
用返回的那个码，比假装它通过了要好得多——Project Owner 看到一条 failed + 存储原因，
会去修存储；看到一条 passed，会去批准一个没人读过的东西。
