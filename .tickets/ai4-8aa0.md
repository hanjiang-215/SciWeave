---
id: ai4-8aa0
status: open
deps: [ai4-tb9k]
links: []
created: 2026-10-22T13:24:04Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, ready-for-agent, work-agent, task-agent]
---
# 套件的 skill、卡片样例和常驻启动

## Parent

最小 Work Agent 实现规格（ai4-z3z4）。套件形态见「建立新 Task Agent 的套件」（ai4-za77）。

## What to build

套件除了能跑的服务，还要让研究员的 Personal Agent 知道怎么换成自己的 Task Agent。skill 教他按样例改 Agent 定义并放进定义槽，不教改 Gateway。libs 里至少有一张可复制的 fast-agent 卡片样例。

两个 gateway 进程在研究员机器上用用户级自启动常驻。hooks 只在打开 harness 时检查，没跑就拉起，不掌管它们的生命周期。关掉 harness 不得停止订阅。

## Acceptance Criteria

- [ ] skill 的读者是 Personal Agent，步骤只覆盖复制卡片、修改指令和允许的领域 MCP、装进定义槽
- [ ] libs 预置至少一张 fast-agent 卡片样例
- [ ] gateway/mcp 与 gateway/subscriber 由用户级自启动拉起，不随 harness 退出
- [ ] hooks 只在打开 harness 时检查并补启动
- [ ] skill 不包含修改状态机、租约或 Gateway 进程的步骤

