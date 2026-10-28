---
name: centre-conflict-matrix
description: 判定同一批候选之间在同一个逻辑对象上的冲突，并把它写成可比较的矩阵。
---

# 冲突矩阵

冲突判定是**同批、同时点**的事。逐个候选判不冲突，合起来却是两个候选改同一个
`logical_id`——这就是这套矩阵存在的唯一理由。

## 为什么必须是一次快照

`list_reviewable_candidates(mapping_domain_id)` 一次返回该域当前的**全量**可送审候选。
在这之后提交的候选不在这一批里，也不该被算进这一批。所以：

- 一轮预审 = 一次 `list_reviewable_candidates` 调用 = 一批；
- 不要在一次预审里多次调用它再合并结果，「同一时点」就不成立了；
- 正式版本发布会让一批候选的基准同时失配（见 `invalidation`），那一轮要重拉。

## 冲突在哪一层

**Mapping**：对象身份是 `logical_id`（`TaskNode` 与 `DependencyEdge` 都有）。同一个
`logical_id` 的两个不同 `version_id` 被两个候选同时改动，就是冲突——不是因为内容不同，
而是因为两条候选分支都想成为它在正式图里的下一个版本。

注意每个 node 的 `@id` 是 `TaskNode/<version_id>`，`version_id` 已由提交者定。所以
「同一逻辑对象」要按 `logical_id` 归并，不能按 `@id` 或 `version_id` 归并，否则同一个
对象的两个候选会被当成两个对象，冲突永远判不出来。

**Wiki**：对象身份是 `document_id`，一次改动落在一个 `WikiRevision` 上。两候选改同一个
`document_id` 即为冲突。引用（`ResourceReference`）不是冲突主体，但指向同一资源版本的
两处不同说法应在 `overlap` 里说明。

## 判定的边界

冲突是**事实**，不是裁决：

- 你只报告「这两个候选在 `logical_id=...` 上重叠」；
- 你不选谁对、不合成第三个候选、不改任何一个候选；
- 解决冲突必须由提交方出新候选，或由 Project Owner 指定其中一条。这两件都不是你的动作。

唯一的例外是**混合候选**：那需要新分支，见 `merged-candidate`，而且它只在
「两条候选各改一半、并不真正冲突」时使用。真冲突时混合会把两个互相矛盾的版本塞进一个分支。

## 写进报告

`append_prereview_log` 的 `conflict_matrix` 参数是数组：

```json
[
  {"candidate_id": "cand-a", "overlap": "TaskNode/logical-7: also changed by cand-b"},
  {"candidate_id": "cand-b", "overlap": "TaskNode/logical-7: also changed by cand-a"}
]
```

两侧都要写。只写一侧会让读报告的人以为另一条候选是干净的。`overlap` 是一句人能读懂的
说明，不是机器可解析的格式——真正需要机器比较的是 `checks` 里的 `failures`。

## 同一逻辑对象之外，还要看什么

- **依赖环**：已经在写入时拒绝（`invalid_dependency_edge`）。不要重复判。
- **入边消失**：一条候选删掉某个节点的入边，会让它从「不可调度」变「可调度」——那不是冲突，
  是影响范围，见 `prereview-checks` 的第四项。
- **跨域**：Mapping 与 Wiki 的候选永不在同一批里。一次 `append_prereview_log` 只写一个域，
  两域的同批判定要分开做、分开写。这不是遗漏，是设计：一次调用同时改两个领域是被明确禁止的。
