---
id: ai4-xem8
status: open
deps: []
links: [ai4-he04, ai4-s12u]
created: 2026-10-21T12:49:00Z
type: feature
priority: 1
assignee: zhanyunfei
tags: [centre-control, buffer, terminusdb]
---
# 中央草稿箱的存储与审核契约

把 2026-10-21 讨论确定的草稿箱设计收敛成可实现的契约：一个 TerminusDB 数据库、两个命名空间、草稿文档字段、固定提交版本的审核语义和一套 MCP 工具。设计记录见 `docs/data-flow/draft-buffer.md`。

## Problem Statement

`sci-weave/centre-control/buffer/` 目前只有一行说明。Research Mapping、LLM-Wiki 都没有「尚未进入候选分支的内容」的落盘位置，也没有承载一审的服务。既有工单把这一步分别写在领域 SQLite 的 Buffer Submission 表里，与「草稿集中存放、由人一审、通过后由人调 MCP 写候选」的模型不一致。

## Solution

中央服务器上一个独立的 Python 子项目 `sci-weave/centre-control/buffer`，用 TerminusDB 作为存储，对外一套 MCP。它保存草稿正文与审核状态，不创建候选、不写领域存储、不发起执行。

一个数据库 `sciweave_draft_domain`，两个命名空间 `mapping` 与 `wiki`，审核人分别是任务节点负责人与 Wiki 负责人。命名空间是文档上的字段；审核人配置在命名空间配置记录上，不逐份草稿复制。

> 修订（2026-10-21）：原设计为两个数据库、三个命名空间，其中 `sciweave_draft_task_agent` 与 `task_agent_design` 随 Task Agent 端侧自持一并删除，依据工单「Task Agent 改由研究员端侧自持」。

## Design

### 文档模型

- 类 `Draft`：`draft_id`、`namespace`、`kind`、`title`、`submitted_by`、`submitted_at`、`status`、`base_formal_revision_id`、`source_task_node_id`、`source_execution_record_id`、`payload`（`sys:JSON`）、`submitted_commit`、`reviewer_id`、`review_decided_at`、`review_reason`、`supersedes_draft_id`。
- 类 `NamespaceConfig`：`namespace`、`reviewer_ids`、`allowed_kinds`、`promotion_target`。
- `@key` 必须用 `Random`。`Lexical` 键遇到字段值中的 `/` 会百分号编码，`@id` 与生成 ID 不一致直接失败（本机 12.0.8 实测）。

### 状态机

```text
drafting → submitted → under_review → accepted → promoted
                     └→ rejected →（修订后重新 submitted）
任意非 promoted 状态 → abandoned
```

审核对象是提交时固定的 `submitted_commit`。提交后草稿正文仍可修改，但不改变本轮审核对象。

### MCP 工具

`create_draft`、`update_draft`、`submit_draft`、`list_drafts`、`read_draft`、`review_draft`、`mark_promoted`。写操作带幂等键；`review_draft` 重复调用返回首次结论。

### 已知存储限制

- GraphQL 支持按字段过滤与 `limit`/`offset`，不支持 `order_by`，排序在服务层做。
- 手写 WOQL 的 JSON-LD 形状易错，查询走 GraphQL。
- 权限按命名空间授予：两个命名空间同库，库级权限不足以区分，需在服务层按命名空间校验。

## Testing Decisions

- 以 MCP 工具调用为主要测试接缝，不检查私有函数或表访问。
- 使用临时命名空间或临时数据库，测试结束清理；不依赖固定端口与真实凭据。
- 覆盖：创建与修改草稿、提交固定 Commit、提交后修改不改变审核对象、按命名空间解析审核人、越权审核被拒、幂等重复审核、驳回后重新提交产生新版本、`promoted` 后只读。
- TerminusDB 行为验证使用仓库固定的 12.0.8 服务，单测用 Fake 存储。

## Acceptance Criteria

- [ ] 一个数据库、两个命名空间与 `Draft`、`NamespaceConfig` 字段按本票实现，`@key` 使用 `Random`
- [ ] 草稿提交固定精确 Commit；提交后修改正文不改变本轮审核对象
- [ ] 审核人从命名空间配置解析并留档，越权审核被拒绝
- [ ] `review_draft` 幂等，重复调用返回首次结论且不产生第二次决定
- [ ] 草稿箱不创建候选、不写领域存储、不发起执行；`promoted` 只记录候选标识与 Commit
- [ ] MCP 工具在临时数据库上的自动化测试通过，且不依赖固定端口或真实凭据

**2026-10-23T08:23:00+08:00**

负责人由 Frank Qi 转交给 zhanyunfei，原因：由 zhanyunfei 继续负责中央草稿箱（buffer）契约的实现与推进。

## Notes

**2026-10-21**

本票由 `docs/data-flow/draft-buffer.md` 收敛而来。该文件第 8 节列出的既有票冲突不由本票裁决：`ai4-mjku`、`ai4-hkdz` 把 Buffer Submission 放在领域 SQLite；`ai4-xrxw` 的状态链把中央预审写在提交上；`ai4-wd5l` 的顺序是「先接纳执行结果、再创建领域草稿」。三张票的负责人需要决定是否接受新模型的改写。

未定项见该文件第 9 节：`mark_promoted` 由谁调用、是否需要跨库统一收件箱、草稿与候选是否要求内容强一致、参与者身份来源。

**2026-10-21T13:08:28Z**

2026-10-21T21:10:00Z

范围收窄，依据「Task Agent 改由研究员端侧自持」(ai4-we38)：中央不再有 task-agent 服务和部署动作，因此不存在「Task Agent 声明式设计稿」这一类草稿。

需要修改的部分（本票仍由 Frank Qi 负责，正文修订随后进行）：

- 删除第二个数据库 `sciweave_draft_task_agent`。
- 删除命名空间 `task_agent_design`，命名空间只保留 `mapping` 与 `wiki`。
- 保留「两个数据库」表述中的 `sciweave_draft_domain` 为唯一数据库。
- 权限按库授予这条不再需要区分库，改为按命名空间授予。

本票其余部分（`Draft` 与 `NamespaceConfig` 字段、固定 `submitted_commit` 的审核语义、幂等审核、已知存储限制）不受影响。
