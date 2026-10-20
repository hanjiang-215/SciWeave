---
id: ai4-m96w
status: closed
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

## Notes

**2026-10-20T14:16:57Z**

2026-10-20：首两条 TDD 切片已完成：认证 MCP 提交后的测试运行时可经查询从 queued 推进到 awaiting_acceptance，或以 runtime_error 推进到 failed；两条路径均保存结果/错误摘要和时间、追加 Worker 租约获取/终结/释放审计。验证：cd sci-weave/task-agent && uv run --package sciweave-task-agent-gateway-mcp python -m unittest discover -s gateway/mcp/tests -v（6 passed）；python3 -m compileall -q gateway/mcp/src；git diff --check。后续仍需补齐适配器端口、租约竞争、跨节点独立执行与短生命周期独立进程。

**2026-10-20T23:55:41Z**

2026-10-21：完成短生命周期独立 Worker 进程调度。Worker 子进程原子领取并释放 SQLite 租约，成功转 awaiting_acceptance；测试运行时经 MCP 查询覆盖成功、异常、超时、非零退出与取消状态，以及同 TaskNode 串行和跨 TaskNode 并行。run、resume、cancel 端口保持可用。健康在 ingest 或 runtime 未配置时分别报告 not_configured。验证：cd sci-weave/task-agent && uv run --package sciweave-task-agent-gateway-mcp python -m unittest discover -s gateway/mcp/tests -v（10 passed）；python3 -m compileall -q gateway/mcp/src；git diff --check。
