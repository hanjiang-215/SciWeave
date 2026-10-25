---
id: ai4-gt3m
status: open
deps: []
links: [ai4-z3z4, ai4-xejt, ai4-lrfz]
created: 2026-10-23T12:45:00Z
type: task
priority: 2
assignee: hanjiang
tags: [centre-agents, gateway, mcp, verification]
---
# Centre Agent gateway/mcp 测试在 Windows 复跑失败与看板 Gateway 来源缺口确认

承载两项向 Centre Agent 实现侧提交确认的事实：`centre-agents/gateway/mcp` 测试在 Windows 环境复跑失败；Web 看板聚合所缺的 Gateway/消息监听只读来源契约仍未提供。本票只记录事实与建议，不改写 `ai4-z3z4`、`ai4-xejt`、`ai4-lrfz` 的内容，由各票负责人裁决。

## 事实一：gateway/mcp 测试在 Windows 复跑失败

在 `sci-weave/centre-control/centre-agents` 执行：

```bash
uv run --locked --package sciweave-task-agent-gateway-mcp python -m unittest discover -s gateway/mcp/tests -v
```

结果 5 项测试中 3 项失败（`FAILED (failures=3)`）：

- `test_fake_candidate_event_runs_fixed_placeholder_to_completed`
- `test_duplicate_event_does_not_create_second_execution`
- `test_same_candidate_is_serialized`

共同错误：spawn 子进程内 `ExecutionStore(database)` 打开临时 SQLite 报 `sqlite3.OperationalError: unable to open database file`（`gateway/mcp/src/gateway/app.py:45` → `store.py:20`）。失败测试全部是需要拉起 `run_worker_process` 子进程的用例；不拉起子进程的 `test_centre_mcp_has_no_owner_submission_or_acceptance` 与 `test_disposition_tools_return_unimplemented` 通过。

对照证据：`ai4-xejt` Notes（2026-10-23T01:47:56Z）记录「centre gateway 5 passed」，与本机复跑结果不一致。最小复现探针（父进程保持 WAL 连接 + spawn 子进程打开同一临时 SQLite）在本机可以成功，说明不是「spawn 无法打开 SQLite」的普遍环境限制；疑似 `TemporaryDirectory` 与 `multiprocessing spawn` 在本机环境（Windows + Python 3.14）的交互问题，或测试/实现侧的路径生命周期问题。归因与修复留给 Centre Agent 侧，本票不给出未验证的结论。

## 事实二：看板 Gateway/消息监听来源契约缺口

`ai4-lrfz` 的 `dashboard-api` 已实现聚合与安全降级，但 Gateway 与消息监听两个来源因缺少稳定只读查询契约而无法配置，只能以 `unavailable/partial` 呈现。已存在的 Gitee issue `IKPT5I`（2026-10-23，作者 hanjiang-215）已列出所需只读能力与约束，本票不重复正文。

## 建议

1. Centre Agent 侧在本机复跑上述 3 项测试确认失败是否可复现；若为 Windows 特有，补充跨平台说明或修复临时路径/子进程生命周期；`ai4-xejt` 的「5 passed」证据需要标注其验证环境。
2. 若 gateway/mcp 测试修复涉及 `ai4-z3z4` 的验收标准「全部测试决策所列行为均有自动化验证」，请该票负责人裁决是否补充 Windows 环境的测试边界。
3. `IKPT5I` 的契约确认进展与 `ai4-lrfz` 的 Gateway/消息监听来源配置保持同步；`ai4-lrfz` 侧在契约就绪前维持 `unavailable/partial` 降级。

## Acceptance Criteria

- [ ] Centre Agent 侧确认 3 项失败是否可复现，并给出归因或修复；`ai4-xejt` 验证证据标注运行环境
- [ ] `IKPT5I` 或等价渠道给出 Gateway/消息监听只读契约的确定进展
- [ ] 本票结案时记录裁决结论与证据，不留下未验证断言

## Notes

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。

**2026-10-23T12:45:00Z**

由 hanjiang 在 `feature/hanjiang` 上审查时发现并记录。依据仓库 ticket 属人规则，本票不改写 Frank Qi 名下 `ai4-z3z4`/`ai4-xejt` 的内容，只作为关联票承载事实与建议。复跑命令与失败签名见上方「事实一」。

**2026-10-23T12:50:00Z**

已向 Gitee 提 issue 通知 Frank Qi：[请 Frank Qi 确认：Centre Agent gateway/mcp 测试复跑失败与看板 Gateway 来源缺口](https://gitee.com/qi-yueran/ai4science/issues/IKQ2KK)，正文首行 @Frank Qi 并列出两项事实、复现命令、失败签名、对照证据与最小复现结论。
