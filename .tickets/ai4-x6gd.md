---
id: ai4-x6gd
status: closed
deps: []
links: [ai4-o2n3]
created: 2026-10-23T02:28:34Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-o2n3
tags: [implementation, ready-for-agent, task-agent, work-agent, toolkit, multi-agent, fast-agent]
---
# 分离 Work Agent runtime 与套件服务模板

## Parent

研究员端侧 Task Agent 与 deploy-task-agent-skills 规格（ai4-o2n3）。

## What to build

把研究员套件中的运行时内核与三个服务角色的启动壳明确分离。运行时负责执行记录投影、Worker Lease、消息幂等和一轮执行；服务模板只负责装配和启动 `gateway/mcp`、`gateway/subscriber` 与 `worker`，不复制运行时逻辑。迁移后套件仍能独立安装和运行，不依赖 Centre Agent 源码。

## Acceptance Criteria

- [ ] 运行时包提供状态记录、Worker Lease、消息幂等和一轮执行的稳定公共接口。
- [ ] 三个服务模板只调用运行时包，不重新实现状态机或租约。
- [ ] 假队列消息能够经过 subscriber、Worker 和假草稿箱并得到 `completed` 与 `draft_id`。
- [ ] 同一目标不并发，重复消息不创建第二条执行记录。
- [ ] 套件安装、源码编译和运行时测试通过，且不对 `centre-agents` 产生 path 依赖。
- [ ] 原有用户级常驻启动边界保持不变。

## Notes

**2026-10-23T02:47:25Z**

2026-10-23：完成运行时与服务模板分离。将 libs 迁移为独立 runtime 包，提供 ExecutionRecord、ExecutionStore、WorkerLease、WorkAgentRuntime 和 run_one；三组件模板仅装配 runtime。验证：runtime 4 tests passed，模板 compileall 通过，git diff --check 通过；不依赖 centre-agents。
