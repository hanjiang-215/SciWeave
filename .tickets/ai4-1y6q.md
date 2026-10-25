---
id: ai4-1y6q
status: open
deps: [ai4-zc85]
links: []
created: 2026-10-23T13:56:20Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-p5f3
tags: [implementation, centre-control, coordinator, handoff, message-queue, ready-for-agent]
---
# 实现 handoff coordinator 依赖重算、等待与派发恢复核心

在 sci-weave/centre-control/coordinator 建立独立 Python 子项目，先实现不依赖具体 MCP/Redpanda 客户端的交接协调核心：正式 Mapping 查询端口、PendingHandoff/HandoffDispatch SQLite 存储、条件重算、task_handoff_ready/human_notification_intent 输出和启动恢复。

## Design

位置：sci-weave/centre-control/coordinator/。独立 pyproject.toml、uv.lock、.env.example、src/main.py、src/coordinator/、tests/。首版用标准库 sqlite3，领域查询、消息发布和通知发布都用 Protocol/port 隔离；不直连 Research Mapping SQLite/TerminusDB，不臆造 MCP/Redpanda SDK。以 Fake ports 验证正式快照、无后继、条件未满足、Agent 不可用、派发结果未知、重复事件和启动扫描。真实 MCP/Redpanda 适配器待接口票 ai4-2982 和消息语义收敛后接入。

## Acceptance Criteria

- 新增符合子项目规范的 Python 服务骨架和锁文件\n- PendingHandoff 与 HandoffDispatch 具备幂等 schema、状态迁移和启动扫描\n- 仅基于正式 Mapping 查询端口判断后继、依赖输出、executor_refs 和终点\n- 条件满足时发布 task_handoff_ready，条件不满足时保存等待事实，确认无后继时发布 task_terminal_summary\n- Agent 不可用和人工路径生成 human_notification_intent，不修改正式 Map\n- 派发结果未知可恢复，重复输入不重复发布\n- 单元测试使用 Fake ports，不依赖真实 MCP、Redpanda、TerminusDB 或凭据\n- README、.env.example、pyproject.toml 记录运行和验证命令\n- 最小安装、测试和 compileall 通过并回写本票 Notes

## Notes

**2026-10-25T06:58:36Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T06:58:36Z。
