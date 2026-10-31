---
name: researcher-use-research-map
description: 读正式 Research Mapping、按精确正式基座提交候选，并读懂提交结果里的每一个状态。
---

# 用 Research Mapping MCP

你以 `researcher` 身份拿到的能力是 `read` + `candidate_submit`。这张卡片上没有
`candidate_review`、`formalize`、`prereview_log`、`merged_candidate`——审、批、预审、合并
都不是研究员的动作。

## 先读正式图

```
get_formal_mapping(mapping_domain_id)
```

返回当前被激活的 Formal MappingRevision 以及它精确指向的那份 TerminusDB 快照。
看到 `no_formal_revision` 是正常状态：这个领域还没有任何正式版本，第一个候选的
`base_formal_revision_id` 只能留空，服务端会返回 `formal_base_required`。

`get_formal_mapping_at_revision(mapping_domain_id, formal_revision_id)` 用来读一个历史版本。
两者都不会返回「branch 最新」的内容：未激活的 Commit 读不到。

## 提交候选

```
submit_candidate(change_set={...}, idempotency_key="...")
```

`change_set` 是一个对象，服务端会做机械校验，**不是**想写什么就写什么：

- `nodes`、`edges` 必须是数组；
- 每个 node 必须是 `@type=TaskNode`，`@id` 必须等于 `TaskNode/<version_id>`，
  且 `logical_id`、`version_id`、`title`、`objective`、`scope`、`task_owner_id`、
  `created_by`、`created_at` 都要是非空字符串；
- `acceptance_criteria`、`expected_outputs`、`required_evidence` 必须是非空数组；
- `mapping_domain_id` 要与 change_set 一致，`lifecycle_state` 必须是 `candidate`，
  `proposal_id` 与 `base_formal_revision_id` 要和 change_set 顶层的一致；
- edge 的 `@id` 必须是 `DependencyEdge/<version_id>`，两端 ref 都要有
  `logical_id` 与 `version_id`。

这些检查是**写时拒绝**：格式、引用、环。基座过期不是写时拒绝，那是预审时的事实，
会由 Centre Agent 的预审报告指出——所以你不需要自己去比基座新旧。

## 读懂返回的 status

| status | 含义 | 你该做什么 |
| --- | --- | --- |
| `submitted` / `confirmed` / `ok` | 候选分支与 commit 已建好 | 记下 `submission_id`、`proposal_id`、`commit_hash` |
| `rejected` + `idempotency_conflict` | 同一个幂等键配了不同的内容 | 这不是重试能解决的；换键或改回原内容 |
| `rejected` + `formal_base_required` | 该带 `base_formal_revision_id` 却没带 | 先 `get_formal_mapping` 拿当前版本，再提交 |
| `rejected` + `invalid_change_set` 等 | 机械校验没过 | 按 reason_code 改 change_set，别改服务端 |
| `failed` | TerminusDB 明确拒绝 | 把 `reason_code` 原样回报，不要猜 |
| `result_unknown` | 存储结果未知 | **不要**换幂等键重试；先用同一个键重放，服务端会返回上次的结果 |

`result_unknown` 是这套流程里唯一需要小心的状态：换键重试会在存储里留下两个候选。

## 提交之后

候选事件会自动发给 Centre Agent 与 Project Owner。你要做的是等待，并在这期间：

- 用 `list_candidates(submission_id)` 查自己那次提交的治理记录（不是整个领域的候选队列——
  那是 `list_reviewable_candidates`，属于 Centre Agent）；
- 收到退回通知时看 `push-task-agent-to-rework`。

## 什么都不要做的时候

不要为了让候选「看起来干净」去改 `.env` 里的能力配置、也不要请人给这张卡片加
`candidate_review`。研究员审自己的候选，整条治理链就没有第二道门了。

## 提交候选 ≠ 任务完成

「任务在看板变成已完成」和「成果进正式地图」是两件事：

- 任务完成 = 研究员在处置面 `review_execution(accepted)`（见 `finish-task`）。
- 成果入库 = 用 `promote-draft` 把草稿提成候选，再由 Project Owner 审核正式化。

不要以为提交了候选，任务就自动算完成了，反过来也一样。
