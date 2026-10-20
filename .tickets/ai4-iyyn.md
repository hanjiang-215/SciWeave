---
id: ai4-iyyn
status: open
deps: [ai4-gqj3, ai4-2h8c]
links: []
created: 2026-10-20T07:46:47Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, task-agent, ready-for-agent]
---
# 最小 Task Agent 项目组端到端验收

## Parent

最小 Task Agent 项目组实现规格（ai4-z3z4）。

## What to build

以认证 MCP 客户端完整验证 Task Agent 项目组的 Owner 命令、调度、Worker、fast-agent、控制、会话恢复和健康行为，并证明本阶段没有引入领域 Buffer 或实际消息队列消费。

## Acceptance Criteria

## Acceptance Criteria

- [ ] 从认证 MCP 接缝验证命令提交、查询、幂等、取消、列表、审核和错误边界。
- [ ] 验证 Worker Lease 串行化、Worker 释放、运行时成功和失败、waiting 恢复、返修及固定会话恢复。
- [ ] 验证 Gateway 重启后读取持久状态和审计，不自动重做 failed 执行。
- [ ] 验证 MCP 与回环 HTTP 健康结果的规定差异，以及未配置 ingest 的明确状态。
- [ ] 运行项目组同步、安装、编译与全部自动化测试；记录命令、结果和遗留风险。
- [ ] 验证未引入领域 Buffer、领域 MCP、实际队列消费或真实模型凭据。

