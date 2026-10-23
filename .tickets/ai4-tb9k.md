---
id: ai4-tb9k
status: open
deps: [ai4-xejt]
links: []
created: 2026-10-22T13:24:04Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, ready-for-agent, work-agent, task-agent]
---
# 研究员套件跑通同一条消息链路

## Parent

最小 Work Agent 实现规格（ai4-z3z4）。套件形态见「建立新 Task Agent 的套件」（ai4-za77）与 ADR-0002。

## What to build

研究员套件里的 libs 和服务模板能独立跑完一轮 Task Agent：假的上游交接消息进来，领取租约，拉起 Worker，假草稿箱返回 draft_id，执行记为 completed。服务模板只负责启动，Gateway 不在模板里再实现一遍。

研究员只能更换 Agent 定义。这套源码不 path 依赖中央 Centre Agent。

## Acceptance Criteria

- [ ] libs 提供状态机、Worker Lease 和拉起子进程；服务模板只启动 gateway/mcp、gateway/subscriber 和 worker
- [ ] 假的上游交接跑完一轮，假草稿箱的 draft_id 记入 completed
- [ ] 同一目标不并发，重复投递不产生第二轮
- [ ] 更换 Agent 定义不会改到状态机或租约
- [ ] 与 Centre Agent 源码没有 path 依赖，测试不依赖真实队列、真实草稿箱或真实模型

