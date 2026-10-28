---
name: researcher-audit-buffer
description: 审自己命名空间里的草稿：看懂状态机、认出卡住的草稿、判断该接受还是驳回。
---

# 审草稿

草稿箱是「还没成为候选」的内容待的地方。它不判断科研内容对错，也不写领域存储——
它只保证审核对象是一份**固定下来的**快照。

## 状态机，以及每个状态你是谁的追问

```text
drafting → submitted → accepted → promoted
                     └→ rejected →（改完重新 submitted）
```

| 状态 | 谁在等 | 你能做什么 |
| --- | --- | --- |
| `drafting` | 作者自己 | `update_draft`（只有 `submitted_by` 本人） |
| `submitted` | 命名空间审核人 | `read_draft(draft_id, submitted_commit)` → `review_draft(accept\|reject)` |
| `accepted` | 人，不是系统 | 手动去领域 MCP 建候选，回来 `mark_promoted` |
| `rejected` | 作者 | 改完再 `submit_draft`；`submitted_commit` 会换成一个新的 |
| `promoted` | 没人 | 只读 |

`accepted` **不产生候选分支**。这是整套流程里最容易出错的一格：接受草稿之后必须有人
调 `submit_candidate` / `submit_wiki_candidate` 才会真的出现候选，然后把候选 id 与 commit
写回 `mark_promoted`。没有 `promote-draft` 那一步，草稿会永远停在 `accepted`，看起来像
「审核通过了但什么都没发生」。

## 审的时候看什么

1. **审的是快照，不是正文**。`submit_draft` 冻结了那一刻的 TerminusDB commit。
   作者之后继续改正文不影响本轮审核对象。所以 `read_draft` 要带 `submitted_commit`，
   不带时读到的是最新正文——那已经不是你在审的东西了。
2. **驳回要写清原因**。`reason` 是作者下一轮唯一的输入。
3. **别替作者改稿**。你不是 `submitted_by`，`update_draft` 会返回 `forbidden`；
   要改就让作者改，那不是你这一格的事。

## 认出卡住的草稿

```text
list_drafts(namespace="mapping"|"wiki", status="submitted")
```

- 长期 `submitted` 且没人审：审核人不到位，不是流程 bug。
- 长期 `accepted` 但领域里没有对应候选：`mark_promoted` 那一步漏了，或者候选提交失败了。
  去 `use-research-map` / `use-research-wiki` 里用 `list_candidates(submission_id)` 核对。
- `rejected` 之后一直没 `submitted`：作者放弃了，或者改不动；问人，不要自己重提交。

## 一件事只有你能做，也只有你不能做

你是自己命名空间的审核人，所以 `review_draft` 与 `mark_promoted` 在这个套件里出现。
这不代表你能审候选：`candidate_review` 与 `formalize` 是 Project Owner 的能力，
这个套件的任何卡片都不带它们。
