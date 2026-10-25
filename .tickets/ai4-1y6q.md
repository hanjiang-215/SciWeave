---
id: ai4-1y6q
status: closed
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

- [x] 新增符合子项目规范的 Python 服务骨架和锁文件
- [x] PendingHandoff 与 HandoffDispatch 具备幂等 schema、状态迁移和启动扫描
- [x] 仅基于正式 Mapping 查询端口判断后继、依赖输出、executor_refs 和终点
- [x] 条件满足时发布 task_handoff_ready，条件不满足时保存等待事实，确认无后继时发布 task_terminal_summary
- [x] Agent 不可用和人工路径生成 human_notification_intent，不修改正式 Map
- [x] 派发结果未知可恢复，重复输入不重复发布
- [x] 单元测试使用 Fake ports，不依赖真实 MCP、Redpanda、TerminusDB 或凭据
- [x] README、.env.example、pyproject.toml 记录运行和验证命令
- [x] 最小安装、测试和 compileall 通过并回写本票 Notes

## Notes

**2026-10-25 实现完成（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

在 `sci-weave/centre-control/coordinator` 落地独立 Python 子项目（pyproject.toml、uv.lock、.env.example、src/main.py、src/coordinator/、tests/）。核心是 `CoordinatorService`，仅依赖标准库与 Fake ports：

- 输入端口：`on_formal_revision_published` 触发全量重算，`on_task_completed` 记录完成事实并重算下游；`startup_scan` 按域名重放最新版本并重试 `result_unknown`/`failed` 派发。快照不可读时静默保留既有事实等待重试。
- 查询端口：`get_formal_mapping_at_revision`（ai4-2982 契约），继任/依赖/executor_refs/终点仅基于该快照判定，不直连领域存储。
- 存储：`PendingHandoff`（唯一键 mapping_domain_id+task_node_id+target_node_version_ref）与 `HandoffDispatch`（唯一键 dedupe_key）幂等 schema，`completed_fact` 记录上游完成事实，`domain_state` 记录每域最新正式版本；全部与自己库隔离。
- 输出：条件满足且执行者可用发布 `task_handoff_ready`；执行者不可用发 `human_notification_intent` 并保留 `waiting` 事实；确认无后继发 `task_terminal_summary`。同一触发重复到达由 dedupe_key 去重，不重复发布。
- 恢复：发布失败置 `result_unknown` 并在启动扫描重发；快照 `unavailable`/`inconsistent`/`no_such_revision` 分别走重试或失败转人工，不降级、不篡改正式 Map。

验证：`uv sync --dev`；`uv run --env-file .env.example pytest -q` 9 passed；`uv run --env-file .env.example python -m compileall -q src tests` 通过。测试覆盖：条件满足派发、条件未满足保留等待、`task_completed` 解除下游、重复事件不重复发布、Agent 不可用转人工、`result_unknown` 启动恢复、快照不可用保持等待、启动扫描保持 waiting 且不重复派发、仅无后继节点触发终点汇总。当前 `src/main.py` 仅加载配置与状态库；真实适配器待 ai4-te1v 消息语义收敛后接入（已在 README 与代码注释说明）。

**2026-10-25T06:58:36Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T06:58:36Z。
