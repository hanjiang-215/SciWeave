---
id: ai4-roow
status: open
deps: [ai4-jckq]
links: [ai4-v869, ai4-jckq]
created: 2026-10-27T04:00:57Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-v869
tags: [enhancement, ready-for-agent, sciencepal, mapping, agent]
---
# SciencePal 执行报告回写地图：草稿、候选与进度两条轨道

外部 harness 完成 SciencePal 执行后，把 ExecutionReport 写入中央草稿箱；TaskNode Owner 一审后由人提交候选，Project Owner 正式化。地图只按路线变更更新；运行状态作为投影，不写进 TaskNode 版本对象。

## Design

报告契约：task_node_id、execution_id、status、sciencepal.run_id、inputs/artifacts sha256、逐条 acceptance、route_change、limitations。没有 run_id 或产物哈希不得写 completed。

草稿：create_draft(namespace=mapping, kind=mapping_change, payload={report, proposed_change_set})；不改草稿箱的 kind 白名单。

候选：候选基准用交接消息的 trigger_revision_id；地图前进后提交得到 stale_base 是正确行为，重新取基准再提交。

进度两条轨道：L0 只在正式化时更新；L1 候选带 progress 快照；L2 运行投影另立服务，本票不做。

权限：harness token 只开 read；candidate_submit 留给人/PO；formalize 永不下放。

## Acceptance Criteria

- [ ] 一份真实 SciencePal run 的 ExecutionReport 能写入草稿箱并读回（draft_id、payload 完整）。
- [ ] 一审接受后，用报告里的 proposed_change_set 提交候选并正式化，正式图出现预期变化（T4）。
- [x] 报告缺产物或哈希不符时不得写 completed；失败报告保留 run_id 与错误码。
- [ ] 审计可关联 execution_id、run_id、draft_id、candidate_id、formal_revision_id。
- [x] 文档明确 L0/L1 边界，不把运行状态写进 TaskNode 版本对象。

## Notes

**2026-10-27 回写链路实现（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`，三者一致。

提交 `54944ee`（`feat(sciencepal-bridge): write execution reports into the draft buffer`）。

已落地（离线可验证）：

- `sciencepal_bridge/report.py`：ExecutionReport 组装与校验。`status=completed` 必须同时有 `sciencepal.run_id` 与至少一个带 `sha256` 的产物，否则拒绝组装；`failed`/`stopped` 报告保留 `run_id`、产物可为空。`proposed_change_set` 从 `route_change.proposal` 派生。
- `sciencepal_bridge/writeback.py`：草稿箱回写客户端。按 `create_draft(namespace=mapping, kind=mapping_change, payload={report, proposed_change_set})` 写入，沿用既有 kind 白名单；带 `source_task_node_id` / `source_execution_record_id` 便于审计串联；结果回填 `execution_id`、`run_id`、`task_node_id`、`draft_id`。
- 入口：CLI `sciencepal report <run_id> --task-node-id ... [--write-draft]`，MCP 工具 `sciencepal_report`（含 `write_draft`、`acceptance_json`、`route_change_json`）。
- 配置：`SCIWEAVE_DRAFT_BUFFER_URL`、`SCIWEAVE_DRAFT_BUFFER_TOKEN`、`SCIWEAVE_BRIDGE_SUBMITTED_BY`（`.env.example` 已登记，令牌不入库）。
- 文档：README 补执行报告回写章节与 L0/L1 边界、权限边界。

验证：

```text
cd sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/custom-mcp/sciencepal-bridge
uv run --locked python -m unittest discover -s tests -q → 35 tests OK（12 原有 + 23 新增）
uv run --locked python -m compileall -q src tests → 0
git diff --check → 0
```

真实草稿箱端到端自检（真实 `DraftBufferService` + 真实 `McpHttpServer` + 真实 HTTP 调用，非 mock）：

```text
create_draft → draft_id 69da8a50-…, status=drafting
read_draft  → payload 键 [proposed_change_set, report]，report.execution_id=exec-e2e，
              artifacts[0].sha256 前 8 位 aaaaaaaa，proposed_change_set.nodes=[{"id":"n2"}]
```

同一次自检还确认权限分离：harness 令牌可以开草稿，但 `read_draft` 被拒（`caller is not authorized for this namespace`），读回与一审必须用命名空间评审身份——与 Design 的「harness token 只开 read；candidate_submit 留给人/PO；formalize 永不下放」一致。

仍缺（需要 SciencePal 真实 token 与运行中的 research-map 才能做）：

1. AC1 的「真实 run」：上面端到端用的是真实草稿箱 + 构造报告；`report` 对真实 `run_id` 取值、`collect` 产物哈希的真实性要等 token 到位后跑一次 `start → status → collect → report --write-draft`。
2. AC2：候选提交与正式化（T4 变化）要接 research-map 的 `submit_candidate` / `formalize_candidate`，并需要 TerminusDB/SQLite 正式图实例。
3. AC4 的 `candidate_id`、`formal_revision_id` 两段：`report` 结果已预留字段（当前为 `null`），需 AC2 走通后回填。

不把运行状态写进 TaskNode 版本对象：本票只产出草稿与报告，`status` 留在报告与本地台账投影里，草稿 payload 不含 TaskNode 版本字段。
