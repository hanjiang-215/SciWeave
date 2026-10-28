---
name: researcher-use-research-wiki
description: 读正式 Wiki 文档、带完整引用集提交 Wiki 候选，并避开引用校验的几个坑。
---

# 用 Research Wiki MCP

你以 `researcher` 身份拿到 `read` + `candidate_submit`。Wiki 侧的三道关：正式基座、
文档结构、引用集。三道都过才会产生候选分支。

## 读

```
get_formal_wiki(wiki_domain_id)
list_wiki_candidates(wiki_domain_id)
```

`get_formal_wiki` 读当前正式 WikiRevision。`list_wiki_candidates` 按领域返回候选提交——
和 Mapping 侧不一样：那边 `list_candidates` 要 `submission_id`（只看自己那次的治理记录），
这边按 `wiki_domain_id` 列，因为你起草一篇文档前需要知道这个领域已经有哪些候选在飞。

## 提交

```
submit_wiki_candidate(document_change={...}, idempotency_key="...")
```

`document_change` 里有四件事：`submission_id`、`proposal_id`、`wiki_domain_id`、`submitter_id`，
外加 `base_formal_revision_id`、`document`、`references`。

`document` 必须是 `@type=WikiRevision`，且这几个字段都不能空：
`wiki_revision_id`、`document_id`、`category`、`title`、`body_markdown`、`created_by`、`created_at`。
`category` 只能是 `source`、`entity`、`concept`、`synthesis`。`created_by` 必须等于 `submitter_id`。

`base_formal_revision_id` **必填**——这一点和 Mapping 不同，Mapping 在没有正式版本时允许空。
Wiki 侧空基座直接 `rejected` + `formal_base_required`。

## 引用集是最容易错的地方

`references` 数组里每一项都必须是 `@type=ResourceReference`，并且：

- `reference_id`、`reference_role` 非空；
- `target_resource_version_id` 与 `target_wiki_revision_id` **恰好有一个**（两个都给或都不给都是错）；
- `source_revision_id` 必须等于 `document.wiki_revision_id`；
- `wiki_domain_id` 缺省时按领域补，给了就必须同域，否则 `cross_domain_reference`；
- 同一个 `reference_id` 不能出现两次。

引用指向一个 Wiki revision 时，服务端会去正式快照里核那一条是否存在；指向资源版本时它核资源。
所以不要用「先提交、等报错再补」的方式试探——每次失败都是一个 `submission_id` 的失败记录。

## 结果

`document_change` 的 status 与 Mapping 同构：`submitted`/`confirmed`、`rejected` + reason_code、
`failed`、`result_unknown`。`result_unknown` 时**用同一个幂等键重放**，不要换键。

## 边界

这张卡片上没有 `preview_wiki_review`、`create_wiki_merge_request`、`decide_wiki_review`、
`formalize_wiki`、`append_prereview_log`、`create_merged_candidate`。预览是审的人做的事，
合并候选是 Centre Agent 的产物，正式化是 Project Owner 的动作。你起草、提交、等。
