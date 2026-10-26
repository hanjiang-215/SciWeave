---
id: ai4-sv1u
status: open
deps: [ai4-8pvm]
links: [ai4-3zxu, ai4-te1v]
created: 2026-10-26T08:21:15Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-3zxu
tags: [implementation, centre-control, shared, message-queue, ready-for-agent]
---
# 消息载荷结构定义

## What to build

把五类消息的载荷从自由字典变成有必填约束的结构：生产方构造消息时就能发现漏字段，而不是等消费方解析时才炸。

规格见 [`2026-10-26-message-envelope-protocol-package-design.md`](../docs/superpowers/specs/2026-10-26-message-envelope-protocol-package-design.md)。

## Acceptance Criteria

- [ ] `task_handoff_ready` 载荷必填：`mapping_domain_id`、`task_node_id`、`target_node_version_ref`、`target_agent_id`、`pending_handoff_id`、`trigger_revision_id`、`upstream_source_refs`、`dependency_edge_version_refs`、`executor_ref_snapshot`。
- [ ] `task_completed` 载荷必填：`mapping_domain_id`、`task_node_id`、`completed_version_ref`、`execution_id`、`draft_id`、`completed_at`、`result_ref`。
- [ ] `formal_revision_published` 载荷必填：`mapping_domain_id`、`formal_revision_id`。
- [ ] `candidate_created` 与 `candidate_head_updated` 载荷必填：`mapping_domain_id`、`candidate_id`。
- [ ] `dependency_edge_version_refs` 只有一个元素时仍是数组，不退化为单值。
- [ ] `executor_ref_snapshot` 可承载多个执行者引用，且有文档说明它只用于审计、不替代当前正式 Map 校验。
- [ ] 缺任一必填字段时抛出「载荷非法」，与格式非法、版本不支持、消息类型未知区分开。
- [ ] 五类载荷各自可往返，且未知可选字段仍被容忍。
- [ ] 单元测试覆盖：五类载荷的正常构造、每类各缺一个必填字段、单元素数组形状、未知可选字段。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 必填字段清单来自 `ai4-te1v`「统一消息信封」，不要在本票改动或增删。
- `human_notification_intent` 与 `task_terminal_summary` 不走 Redpanda，不属于本包。
- 载荷结构化的价值是尽早失败。消费方仍需容忍未知字段，所以「校验严格」只作用于必填项，不作用于多余项。
