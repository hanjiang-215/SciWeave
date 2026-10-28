---
id: ai4-e4q5
status: closed
deps: []
links: []
created: 2026-10-28T20:21:05Z
type: bug
priority: 1
assignee: hanjiang
---
# subscriber 缺少 task_completed 生产者，下游永不解除阻塞

worker 执行完成写入 execution_records=completed，但无任何组件向 Kafka 发布 task_completed 事件（B6）。协调器已实现消费端（adapter_events._handle_task_completed → service.on_task_completed），故 completed_fact 恒空、下游任务恒 blocking_dependency_missing、看板 completed 恒 0。缺陷报告以 _publish_completed.py 手工模拟已证明消费端逻辑正确，纯缺生产端。

## Design

在 subscriber worker_runner 完成分支，用 shared/message-envelope 的 task_completed 模型（task_node_id/node_version_ref/formal_revision_id/mapping_domain_id）序列化后发布到 sciweave.governance-events。不得改动消费端语义。

## Acceptance Criteria

派发→执行→完成→completed_fact 落库→下游 T2 由 blocking_dependency_missing 转 waiting 全自动完成，无人工模拟；单测断言 worker 完成时发布 1 条 task_completed 且字段齐全。


## Notes

**2026-10-29 / hanjiang**

已实现并验证（提交 30fdd9a，feat(subscriber): publish task_completed）：
- execution_records 新增 mapping_domain_id 列（ALTER 幂等迁移），handle_message 落库域名。
- 新增 completion_publisher.py：KafkaCompletionPublisher 在完成分支发布 	ask_completed 到 sciweave.governance-events；信封同时带 completed_version_ref（schema）与 
ode_version_ref（协调器路由读取）及 ormal_revision_id；best-effort，发布失败仅告警不影响执行。
- 由 SCIWEAVE_GOVERNANCE_KAFKA_BOOTSTRAP 开启；未设置时行为不变。
- 测试：subscriber 30 passed（含 3 项新增：完成发布、失败不发布、信封字段）。
- 回归：coordinator/registry/research-map/research-wiki 全绿。
