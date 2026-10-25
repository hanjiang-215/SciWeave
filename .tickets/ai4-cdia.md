---
id: ai4-cdia
status: open
deps: []
links: [ai4-za77, ai4-8aa0, ai4-o2n3]
created: 2026-10-23T02:18:54Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-z3z4
tags: [toolkit, task-agent, multi-agent, fast-agent, skills, spec, ready-for-agent]
---
# 研究员 Task Agent 技能组与多 Agent 资源边界

为研究员端侧 Task Agent 建立一个名为 deploy-task-agent-skills 的技能组，并收敛技能、Agent 定义、Agent 资源库、MCP 资源库与 fast-agent 多 Agent 工作流的可交付边界。

技能组支持 Router、Orchestrator、Parallel、Agents as Tools 四类内部工作流；平台提供标准资源，研究员可在 local-agent-libs 与 local-mcp-libs 增加自定义资源。多 Agent 仍运行在一个 Work Agent Worker 内，共享一个平台级 ExecutionRecord，最终由最终写入 Agent 产生一个 draft_id。

本票只做规格和资源组织决策，不实现多 Worker 分布式编排。

## Design

## 需要收敛的功能

- deploy-task-agent-skills 的目录、触发条件和 references 组织。
- agent-definitions、agent-libs、mcp-libs、runtime、service-template 的边界。
- Agent 定义与 workflow 定义的 schema。
- Router、Orchestrator、Parallel、Agents as Tools 的配置与组合约束。
- 技能文本对 Agent 行为的约束范围，以及当前不做服务端强制拦截的事实。
- 平台标准资源与研究员 local-agent-libs/local-mcp-libs 的覆盖、版本和加载规则。
- 子 Agent 的 MCP 使用约定、最终写入 Agent 和 draft_id 归属。

## 当前边界

一个平台级 Work Agent 对应一个 Worker、一个 ExecutionRecord 和一个最终 draft_id；多个内部 Agent 通过 fast-agent 工作流协作。子 Agent 不单独取得消息队列消费者组、Worker Lease 或平台级 ExecutionRecord。

## Acceptance Criteria

## 验收标准

- [ ] 技能组目录固定为 deploy-task-agent-skills，并拆分为多个短技能；每个技能有独立 references/ 长文档。
- [ ] 明确 create、compose workflow、configure MCP、validate、troubleshoot 等技能的职责和触发条件。
- [ ] 明确 agent-definitions、agent-libs、mcp-libs、runtime、service-template 的职责边界。
- [ ] 定义 Router、Orchestrator、Parallel、Agents as Tools 的最小配置模型和组合限制。
- [ ] 明确平台标准资源与 local-agent-libs、local-mcp-libs 自定义资源的加载和覆盖规则。
- [ ] 明确技能文本约束不是服务端权限边界，并定义 MCP 调用与最终草稿写入的行为约定。
- [ ] 明确单 Worker、单 ExecutionRecord、单最终 draft_id 的多 Agent 运行边界。
- [ ] 形成可交给后续实现票的目录结构、schema、示例和验证场景。

## Notes

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。
