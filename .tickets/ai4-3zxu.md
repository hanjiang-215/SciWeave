---
id: ai4-3zxu
status: open
deps: [ai4-te1v]
links: [ai4-edrp, ai4-10ja, ai4-f985]
created: 2026-10-26T07:49:53Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-te1v
tags: [implementation, centre-control, shared, message-queue]
---
# 实现消息信封纯协议包

## Background

`ai4-te1v` 把统一消息信封定在 `sci-weave/centre-control/shared/message-envelope/`，但那个目录**不存在**：`sci-weave/centre-control/shared/` 下只有 `audit-trail`。全仓库只有 `ai4-te1v`、`ai4-10ja`、`ai4-edrp` 提过这个路径，没有一张票负责建它。

后果是具体的：`HandoffPublisherPort` 的实现既等 Redpanda 客户端，也等这个包；`ai4-10ja` 明说了不动它。

## Scope

在 `sci-weave/centre-control/shared/message-envelope/` 实现纯协议包。

### 必须遵守的边界

按 `ai4-te1v`「消息信封归属与依赖边界」，这个包**只做** schema 定义、序列化、反序列化、信封构造与校验。它**不持有** Kafka 客户端、连接、消费者和重试循环。各角色自行接入 `confluent-kafka`。

按 `docs/TECH_STACK.md` 的共享代码规则，`shared/` 是代码归属边界，本身不是可部署子项目，**不提交组级锁文件**。

### 内容

- 统一信封的数据结构与 JSON（UTF-8）编解码：`message_id`、`message_type`、`schema_version`、`dedupe_key`、`occurred_at`、`published_at`、`producer`、`routing`、`payload`。
- 三类消息的 payload 结构：`task_handoff_ready`、`task_completed`、以及治理事件 `candidate_created` / `candidate_head_updated` / `formal_revision_published`。
- `task_handoff_ready` 的 payload 必须包含 `dependency_edge_version_refs`（数组，单元素也保持数组形式）与 `executor_ref_snapshot`。
- 校验：必填字段、类型、时间格式、`schema_version` 相等判定。
- 容忍式读取：反序列化保留未知字段而不报错，消费方能够忽略它们。

### schema 版本策略

严格按 `ai4-te1v`「序列化与 schema 版本兼容」实现：

- `schema_version` 是整数精确匹配，不做次版本号。
- `schema_version` 不等即视为不支持，抛出明确错误，由调用方写入可观察 Inbox 状态。
- 新增字段必须可选并有文档化默认值。
- 已有字段名不得改变用途。

## Acceptance Criteria

- [ ] `sci-weave/centre-control/shared/message-envelope/` 下有包实现与 `pyproject.toml`，无锁文件。
- [ ] 信封与三类消息 payload 均有数据结构定义，字段与 `ai4-te1v` 正文一致。
- [ ] 提供信封构造、JSON 序列化、反序列化与校验的公开接口。
- [ ] `schema_version` 不等时抛出可区分的错误，不与「格式非法」混为一类。
- [ ] 反序列化遇到未知 payload 字段不报错，且能在往返（序列化→反序列化→再序列化）中保留或安全忽略。
- [ ] `task_handoff_ready` 缺少 `dependency_edge_version_refs` 时校验失败。
- [ ] `dependency_edge_version_refs` 只有一个元素时仍是数组。
- [ ] 单元测试覆盖：正常往返、未知字段容忍、`schema_version` 不匹配、必填字段缺失、时间格式非法。
- [ ] 包内不出现任何 Kafka 客户端导入；用测试或导入检查断言这一点。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 本票不实现 Redpanda producer/consumer，也不实现 topic 管理。那些属于 `HandoffPublisherPort` 的适配器票。
- 本票不定 topic 名称、分区键或消费者组；全部已由 `ai4-te1v` 定死，照抄即可。
- 序列化选 JSON 而非 Avro 是 `ai4-te1v` 第五轮的裁决，理由与代价写在那张票里。不要在本票重新论证。
- `email-service` 不消费 Redpanda，`human_notification_intent` 与 `task_terminal_summary` 不走本包，只走 MCP。

**2026-10-26 负责人转交（hanjiang 操作，按项目所有者指示）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据：项目所有者 2026-10-26 指示，Frank Qi 名下 coordinator / handoff / message-envelope 链路的 11 张 open 票统一转交 hanjiang 推进与收口。原负责人 Frank Qi，转交时间 2026-10-26T15:41:00Z。转交只变更归属并记录，不改写正文、验收标准与既有决策。
