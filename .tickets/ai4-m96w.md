---
id: ai4-m96w
status: open
deps: [ai4-p19z]
links: []
created: 2026-10-20T07:46:47Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, task-agent, ready-for-agent]
---
# 带 Worker Lease 的本地调度与测试运行时

## Parent

最小 Task Agent 项目组实现规格（ai4-z3z4）。

## What to build

一条经 MCP 创建的 queued 执行可由短生命周期 Worker 和测试运行时完成。Gateway 组件组以共享 SQLite Worker Lease 作为唯一启动权，从而使同一 TaskNode 串行、跨 TaskNode 可独立执行。

## Acceptance Criteria

## Acceptance Criteria

- [ ] 已排队的执行可启动一次短生命周期 Worker，并将成功结果转为 `awaiting_acceptance`。
- [ ] Runtime Adapter 端口支持 run、resume、cancel；测试运行时可验证成功、异常、超时、非零退出和取消的外部状态。
- [ ] 同一 TaskNode 的竞争领取只能得到一条有效租约，未领取者不得启动 Worker；跨 TaskNode 可独立执行。
- [ ] Worker 生命周期、租约领取与释放、状态迁移和错误摘要均追加审计。
- [ ] 未配置 ingest 队列或 Worker runtime 时，健康结果明确报告 `not_configured` 或规定的降级状态。
- [ ] 自动化测试从 MCP 查询和持久化可观察行为验证调度，不依赖调度器私有实现。

