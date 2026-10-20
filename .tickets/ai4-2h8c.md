---
id: ai4-2h8c
status: open
deps: [ai4-m96w]
links: []
created: 2026-10-20T07:46:47Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, task-agent, ready-for-agent]
---
# fast-agent Runtime Adapter 与固定会话恢复

## Parent

最小 Task Agent 项目组实现规格（ai4-z3z4）。

## What to build

Worker 通过实际 fast-agent Runtime Adapter 和不需真实模型凭据的 passthrough 运行时，使用 TaskNode 的固定 session_id 与持久 home 完成首次执行及新进程恢复。

## Acceptance Criteria

## Acceptance Criteria

- [ ] fast-agent 依赖在项目组清单和唯一锁文件中声明，并在票据 Notes 记录来源、用途、版本约束、许可证或限制和验证命令。
- [ ] 首次 Worker 使用固定 session_id、持久 home、connection scope 和 session history 完成一次 passthrough loop。
- [ ] 新短生命周期 Worker 可用同一 TaskNode 会话完成后续一次恢复执行；不同 TaskNode 不共享会话。
- [ ] 默认关闭自动 compaction，Worker 每次 loop 后退出并保留受配置控制的会话文件。
- [ ] fast-agent 故障、会话恢复失败和持久目录不可用均形成可查询 failed 执行和无敏感信息审计。
- [ ] 集成测试不使用或保存真实模型凭据。
