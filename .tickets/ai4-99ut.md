---
id: ai4-99ut
status: closed
deps: [ai4-mx7h, ai4-83uk]
links: [ai4-o2n3]
created: 2026-10-23T02:28:34Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-o2n3
tags: [implementation, ready-for-agent, task-agent, work-agent, toolkit, multi-agent, fast-agent]
---
# 单 Worker 内的多 Agent 工作流执行

## Parent

研究员端侧 Task Agent 与 deploy-task-agent-skills 规格（ai4-o2n3）。

## What to build

在一个短生命周期 Worker 内接入四种 fast-agent 多 Agent 工作流：Router、Orchestrator、Parallel 和 Agents as Tools。工作流共享一个平台级 ExecutionRecord 和 Worker Lease；子 Agent 只产生中间结果，最终写入 Agent 负责合成并调用假草稿箱，整轮执行只产生一个 `draft_id`。

## Blocked by

- agent-libs 标准资源与本地扩展（ai4-mx7h）
- mcp-libs 标准 MCP 资源与本地扩展（ai4-83uk）

## Acceptance Criteria

- [ ] 四种工作流都能由配置启动并完成假任务。
- [ ] Router 能选择子 Agent，Orchestrator 能拆分和汇总，Parallel 能并行独立子 Agent，Agents as Tools 能由主 Agent 调用子 Agent。
- [ ] 子 Agent 不创建额外平台级 ExecutionRecord、消费者组或 Worker Lease。
- [ ] 最终写入 Agent 负责唯一草稿提交，并在 `completed` 记录中保存唯一 `draft_id`。
- [ ] 同一 Work Agent 仍只使用一个 Worker Lease，且不依赖真实模型或真实 MCP。
- [ ] 子 Agent 失败时主工作流返回可观察的稳定失败结果。

## Notes

**2026-10-23T03:09:21Z**

2026-10-23：完成单 Worker 多 Agent 工作流执行。支持 Router、Orchestrator、Parallel、Agents as Tools；子 Agent 只产生中间结果，共享一个平台 ExecutionRecord 和 Worker Lease；最终写入 Agent 只创建一个 draft_id；子 Agent 失败返回 child_agent_failed 且不写草稿。验证：runtime 11 tests passed，compileall 通过，git diff --check 通过。
