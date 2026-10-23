---
id: ai4-jbci
status: closed
deps: [ai4-mx7h, ai4-83uk, ai4-99ut]
links: [ai4-o2n3]
created: 2026-10-23T02:28:34Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-o2n3
tags: [implementation, ready-for-agent, task-agent, work-agent, toolkit, multi-agent, fast-agent]
---
# deploy-task-agent-skills 技能组与端到端套件验证

## Parent

研究员端侧 Task Agent 与 deploy-task-agent-skills 规格（ai4-o2n3）。

## What to build

把研究员侧使用说明组织为名为 `deploy-task-agent-skills` 的技能组。拆分创建 Agent、组合工作流、配置 MCP、验证 Task Agent 和排障等短技能，每个技能提供独立 `references/`。技能组应引导 Personal Agent 只修改 Agent 定义、工作流和资源配置，不修改 runtime、租约或 Gateway；并用假上游消息跑通 subscriber、Worker、多 Agent 工作流、假草稿箱和唯一 `draft_id`。

## Blocked by

- agent-libs 标准资源与本地扩展（ai4-mx7h）
- mcp-libs 标准 MCP 资源与本地扩展（ai4-83uk）
- 单 Worker 内的多 Agent 工作流执行（ai4-99ut）

## Acceptance Criteria

- [ ] 技能组目录固定为 `deploy-task-agent-skills`，包含多个短技能，每个技能有独立 `references/`。
- [ ] 技能覆盖创建 Agent、组合 Router/Orchestrator/Parallel/Agents as Tools、配置 MCP、验证和排障。
- [ ] Personal Agent 按技能可以完成 Agent 定义、工作流和 MCP 资源配置，且不会修改 runtime、Worker Lease 或 Gateway。
- [ ] 假上游消息能够跑完 subscriber、Worker、多 Agent 工作流和假草稿箱，得到唯一 `draft_id`。
- [ ] 用户级常驻服务和 harness 打开时检查 hook 保持有效，关闭 harness 不停止常驻服务。
- [ ] 端到端验证不依赖真实队列、真实模型、真实 MCP 或固定端口。

## Notes

**2026-10-23T03:18:59Z**

2026-10-23：完成 deploy-task-agent-skills 技能组与端到端验证。技能组包含 create-agent、compose-workflow、configure-mcp、verify-task-agent、troubleshoot 五个短技能，每个带独立 references；Personal Agent 只修改定义、工作流和资源配置。新增假上游→subscriber→Worker→Parallel 工作流→假草稿箱→唯一 draft_id 测试。补充验证 MCP catalog 可观察。验证：runtime 12 tests passed，compileall、hook bash -n、git diff --check 通过。
