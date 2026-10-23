---
id: ai4-xejt
status: in_progress
deps: [ai4-3xsp]
links: []
created: 2026-10-22T13:24:04Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, ready-for-agent, work-agent, centre-agent]
---
# Centre Agent 用固定定义跑完一轮

## Parent

最小 Work Agent 实现规格（ai4-z3z4）。

## What to build

中央 Centre Agent 收到一条候选事件后，自己跑完一轮：创建执行记录、领到 Worker Lease、拉起短生命周期 Worker，结束为 completed。Agent 定义写死，只做占位，不实现预审规则，也不把结果写成科研草稿。

同一目标不能并发第二轮。重复投递不能再跑一轮。测试用假队列，不连接真实消息队列。

处置面不另开票。返修、放弃、转人工、回答提问在本票返回 `unimplemented`。列出待审、查看报告、要求重算留给预审规格，不在本票实现。没有 `submit_owner_command`，也没有 `accept`。

## Acceptance Criteria

- [ ] 一条假的候选事件创建执行、领到租约并拉起 Worker，结束后为 completed
- [ ] 同一目标的第二轮在第一轮结束前不能启动
- [ ] 重复投递不产生第二轮执行
- [ ] Agent 定义是固定占位，不包含预审规则，不写入科研草稿
- [ ] 返修、放弃、转人工、回答提问返回 `unimplemented`；不存在 `submit_owner_command` 和 `accept`
- [ ] 测试不依赖真实队列或真实模型


## Notes

**2026-10-23T01:47:56Z**

2026-10-23：完成 Centre Agent 固定定义一轮执行。新增候选事件入口（candidate_id、event_type、event_id），事件以业务键幂等，触发短生命周期 Worker；同一候选通过 Worker Lease 串行，重复事件不创建第二条 ExecutionRecord。固定占位运行时完成为 completed，不实现预审规则或草稿写入。Centre MCP 删除 submit_owner_command，不提供 accept；answer_question 与 review_execution 返回 unimplemented。验证：centre gateway 5 passed，worker 4 passed，compileall 通过，git diff --check 通过；测试使用临时 SQLite、假队列和占位运行时。
