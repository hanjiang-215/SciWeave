---
name: centre-invalidation
description: 候选头或正式基座动了之后，用追加判定表达失效——不改历史报告，也不冻结全体。
---

# 失效判定

一份预审报告只在两个时点仍然成立时有效：产生它的 `candidate_head` 与
`base_formal_revision_id`。任一移动，报告就失效。失效的表达方式只有一种：
**追加一条判定**。

## 两个原因，两条规矩

```
append_prereview_log(
  mapping_domain_id="...",       # 或 wiki_domain_id
  candidate_id="...", candidate_head="...",
  reason="head_moved" | "base_moved",
  superseding_report_id="...",   # head_moved 必填
)
```

| reason | 什么时候 | 额外要求 |
| --- | --- | --- |
| `head_moved` | 候选有了新 head，旧报告对应的是旧内容 | 必须带 `superseding_report_id`，指向新 head 上那份报告 |
| `base_moved` | 正式版本发布了，候选的基准变成旧版本 | 不需要 superseding；重算完成前该候选卡住 |

两点容易踩：

- `head_moved` 不带 `superseding_report_id` 会被拒（`invalid_arguments`）。没有新报告的
  「失效」等于让候选既没有有效报告也没有下一步，那是把门禁变成黑洞。
- 目标候选 head 上**没有任何当前报告**时返回 `report_not_found`。这不是让你去补一条报告，
  而是说明这条候选本来就该走一次正常预审。

## 别把失效当放行，也别冻结全体

- **失效 ≠ 放行。** 门禁是硬的：没有当前报告的候选不能被批准，没有例外。
- **失效 ≠ 冻结全体。** 粒度是单个候选。`base_moved` 只影响那些基准与刚发布的版本不同的
  候选；基准正好等于新版本的候选完全不受影响。这就是 `gateway/ingest` 里
  `_depends_on_older_base` 的那条判断——它不是优化，是正确性。

## 什么时候由谁触发

`gateway/ingest` 已经在做这件事，你通常不需要手工调：

- 收到 `formal_revision_published`：对每个基准与它不同的候选，若当前报告状态是
  `report_current`，追加一条 `base_moved`，并把候选列为需要重算。
- 收到 `candidate_created` / `candidate_head_updated`：按窗口去抖后触发一次全量快照重审
  （默认 60 秒窗口，一轮预审覆盖全量候选，所以同一窗口里多次 head 更新只值一次重算）。

手工调用只在补录时用：例如 ingest 停了半天、事件被跳过，事后发现某个候选的报告明明已经
不该算数却还是 `report_current`。补录前先确认报告的 `candidate_head` 与候选当前 head
确实不同，否则你会把一条有效报告判成失效，然后它必须重算才能再送审。

## 报告状态怎么读

`list_reviewable_candidates` 返回的每个候选都带 `prereview_status`：

| 状态 | 含义 | 谁能往下走 |
| --- | --- | --- |
| `missing_report` | 从没预审过 | 先跑一轮预审 |
| `report_current` | 最新结论对这一 head 有效 | Project Owner 可以决定 |
| `report_stale` | 已被判定失效 | 重算，重算前卡住 |

看到 `report_stale` 就重算，不要试图让它「恢复有效」——日志只追加，没有撤回。
