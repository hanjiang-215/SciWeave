---
name: centre-prereview-checks
description: 对候选分支做一轮预审：四项检查、判据版本、结论怎么写进只追加的日志。
---

# 预审检查

预审的对象是**候选分支**，不是草稿。草稿是研究员与自己那台机器的一审材料，你不看它。

## 一轮预审的输入

```
list_reviewable_candidates(mapping_domain_id)      # 或 list_reviewable_wiki_candidates
```

一次调用返回**同一时点的全量**可送审候选：未放弃、未正式化、未驳回。每个候选带
精确 `candidate_head`、`base_formal_revision_id`、正文快照，以及 `snapshot_status`。

- 不要逐条候选单独预审。冲突判定要求同一时点的一致性快照；逐条会把两个前后脚提交的
  候选误判为不冲突，而这正是冲突矩阵要防的事。
- 不按基准版本过滤。基准过旧的候选同样纳入，只标 `stale`——Project Owner 需要在一处看到全貌。
- `snapshot_status` 不是 `available` 的候选**没有正文**。它不能靠猜，也不能跳过不说：
  在报告里给它一条失败检查，`reason_code` 用返回的 `reason_code`（例如
  `candidate_store_unavailable`）。

## 四项检查

格式、对象引用、依赖关系三项已经在领域 MCP 写入候选时被拒绝（`invalid_change_set`、
`invalid_task_node`、`invalid_dependency_edge` 等），所以你的输入永远是干净候选。
不要再实现这三项，也不要把「格式对不对」写进报告——那会让报告看起来更全面，但只是在
重复一次已经发生过的拒绝。

| 检查 | 输入 | 判定 | 失败后 |
| --- | --- | --- | --- |
| 权限范围 | `submitter_id`、目标单元的操作权限、审核人 | 越权即失败 | 报告事实；补授权不是你的事 |
| 基准版本 | 候选的 `base_formal_revision_id` vs 当前正式版本 | 不相等即 `stale` | 报告事实，不改 Proposal 状态 |
| 冲突 | 同批候选在同一逻辑对象上的改动 | 重叠即 `conflict` | 报告事实，须由提交方出新候选解决 |
| 影响范围 | 从不可调度变可调度、受影响的资源引用与执行记录 | 说不清影响即不通过 | 报告事实 |

**`stale` 与 `conflict` 是报告里的事实列，不是 Proposal 状态。** 你不改候选、不改 Proposal、
不建 Merge Request Buffer。候选怎么处置由 Project Owner 在批准或驳回时决定。

## 判据版本

报告必须带 `rule_set_version`，并且这个版本要能在领域 MCP 的
`SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR` / `SCIWEAVE_WIKI_PREREVIEW_RULES_DIR` 里解析到
一个 `<version>.json`（至少含 `version` 与 `checks`）。解析不到时 `append_prereview_log`
直接返回 `rule_set_missing`——不要改成随便一个版本号重试，那会让同一批候选在不同判据下
得出无法比较的结论。

只记版本号与检查项清单，不记提示词全文。规则文件本身在仓库里受 Git 版本化。

## 写结论

```
append_prereview_log(
  mapping_domain_id="...",            # Wiki 侧是 wiki_domain_id
  candidate_id="...", candidate_head="...",
  base_formal_revision_id="...",
  rule_set_version="1.0.0",
  verdict="passed" | "failed",
  checks=[{"name": "...", "verdict": "passed|failed", "reason_code": "...", "evidence_summary": "..."}],
  conflict_matrix=[{"candidate_id": "...", "overlap": "..."}],
)
```

- **只追加。** 同一 `(candidate_id, candidate_head, rule_set_version, base_formal_revision_id)`
  重复调用返回上一条（`duplicate=true`），不会产生第二条。
- `checks` 不能是空数组；每条至少要有 `name` 与 `verdict`。
- `verdict=passed` 只表示「可以送 Project Owner 选择」，不表示批准。汇报时别把
  `passed` 说成「通过了」。

## 通过之后

发一条 `prereview_completed` 通知给 Project Owner（见 `mcp/email-service`）。通知里
只放结论、候选 id 与 head、以及需要他决定的事；不要把正文抄进去——通知是提示，不是第二份记录。

## 你不能做的

- `formalize_candidate` / `formalize_wiki` / `decide_wiki_review` / `record_review`：批准是
  Project Owner 的动作。你能读所有域的候选，但一个都不能批。
- 进草稿箱。
- 派发任务、判断「下一步该谁动」。
