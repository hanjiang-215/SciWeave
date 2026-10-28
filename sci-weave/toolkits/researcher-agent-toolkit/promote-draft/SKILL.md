---
name: researcher-promote-draft
description: 把一份已接受的草稿推进成领域候选，并回写草稿箱——包括那一步最容易被忘掉的 mark_promoted。
---

# 从草稿到候选

草稿箱的 `accepted` **不等于**已经产生候选。这一步是纯人工的两段动作，中间没有回调、
没有跨服务事务，两边都可能只做一半：

```text
草稿箱 accepted
   ↓  ① 人调领域 MCP 的 submit_candidate / submit_wiki_candidate
领域候选分支 + commit
   ↓  ② 人调草稿箱 mark_promoted(draft_id, candidate_id, candidate_commit)
草稿箱 promoted
```

漏掉 ①，草稿停在 `accepted` 而领域里什么都没有。漏掉 ②，候选在飞而草稿箱还以为没人处理。
两种都会被 `audit-buffer` 里的「卡住的草稿」检查抓到。

## 1. 取出冻结的正文

```
read_draft(draft_id, submitted_commit="<审核时的那个 commit>")
```

必须带 `submitted_commit`。不带时读到的是作者后来改过的正文，而审核人通过的是旧快照。
两者不一致时 `read_draft` 会返回 `submitted_commit_mismatch`——那是保护，不是故障。

`draft.payload` 是原样存放的 `sys:JSON`，按 `kind` 解释：

- `mapping` 命名空间的 `mapping_change`：payload 就是 `change_set` 的素材；
- `wiki` 命名空间的 `wiki_document`：payload 里是 `document` 与 `references`。

## 2. 建候选

Mapping：

```
submit_candidate(change_set={...}, idempotency_key="promote-<draft_id>")
```

Wiki：

```
submit_wiki_candidate(document_change={...}, idempotency_key="promote-<draft_id>")
```

两边的机械校验都在 `use-research-map` / `use-research-wiki` 里写了。这里只强调一件事：
**幂等键用草稿 id 派生**。同一份草稿被两个人同时推进时，第二个人的调用会命中幂等冲突
而不是造出第二个候选。

拿到返回里的 `proposal_id` 与 `commit_hash`（Mapping）或候选 commit（Wiki）。

## 3. 回写

```
mark_promoted(
  draft_id="<draft_id>",
  candidate_id="<proposal_id>",
  candidate_commit="<commit_hash>",
  idempotency_key="promote-<draft_id>",
)
```

`candidate_id` 与 `candidate_commit` 必须非空，否则 `invalid_candidate`。
草稿不是 `accepted` 时 `invalid_transition`——包括已经是 `promoted` 的（重复回写没有意义，
它已经是终态）。

## 4. 顺序错了怎么补

- ① 成功、② 失败：直接重放 ②。`mark_promoted` 是幂等的，草稿还是 `accepted`。
- ① 失败、② 没做：草稿仍是 `accepted`，改 change_set 重新 ①。幂等键要换——上一次
  调用已经用掉了那个键。
- ① 返回 `result_unknown`：**先用同一个键重放 ①**。直接换键会造出第二个候选，
  然后你就无法用一份草稿解释两个候选了。

## 不要做的事

不要为了省一步去调 `formalize_candidate` / `formalize_wiki`——那不是「提交候选的更彻底版本」，
它是 Project Owner 的批准动作，研究员的令牌在这两个工具上会被拒。这个套件的卡片上也没有它们。
