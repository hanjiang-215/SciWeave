---
id: ai4-25wy
status: closed
deps: [ai4-upsm]
links: [ai4-8k4y]
created: 2026-10-21T12:15:20Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, centre-agents, message-queue]
---
# 中央 Agent 的消息队列事件入口

定义中央 Agent 需要消费和产生哪些事件：谁发、什么形状、幂等键是什么、重复投递如何处理。这是当前唯一完全空白的能力。

## Design

Gateway 在 `sci-weave/task-agent` 里已有组件组形态（`gateway/mcp` 与 `gateway/ingest` 共享 SQLite 与串行化约束），`gateway/ingest` 只有骨架，消息队列产品尚未选型。本票不重复选型，只定义中央 Agent 侧的事件契约。

候选事件：上游交接就绪、执行进入待接纳、节点负责人已接纳、Project Owner 已批准、失败需重试。

待定：复用 Gateway 的 ingest 进程还是独立消费者、订阅方式。

## Acceptance Criteria

- 每条事件有稳定名称、形状与幂等键
- 重复投递不产生重复副作用
- 事件不承载审核决定，只承载触发
- 与留痕工具的调用关系明确


## Notes

**2026-10-21T12:48:15Z**

2026-10-21 关闭：随调度职责取消，「上游交接就绪」「执行进入待接纳」「已接纳」「已批准」等触发事件不再由中央 Agent 消费或产生。部署完成通知并入 ai4-s12u。消息队列本身的选型与 Gateway ingest 实现不属于中央 Agent 职责。
