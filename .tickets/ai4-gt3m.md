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

## 事实一：gateway/mcp 测试在 Windows 复跑失败（已确认并修复）

在 `sci-weave/centre-control/centre-agents` 执行：

```bash
uv run --locked --package sciweave-task-agent-gateway-mcp python -m unittest discover -s gateway/mcp/tests -v
```

原结果 5 项测试中 3 项失败（`FAILED (failures=3)`）：

- `test_fake_candidate_event_runs_fixed_placeholder_to_completed`
- `test_duplicate_event_does_not_create_second_execution`
- `test_same_candidate_is_serialized`

共同错误：spawn 子进程内 `ExecutionStore(database)` 打开临时 SQLite 报 `sqlite3.OperationalError: unable to open database file`（`gateway/mcp/src/gateway/app.py:45` → `store.py:20`）。

**2026-10-25 归因与修复（hanjiang，本次更新）**：复现后做最小探针二分定位，结论是 **Windows + Python 3.14 下 `multiprocessing spawn` 子进程冷启动耗时超过测试 `wait_for` 的 2 秒超时**：子进程要重新 import `openai`/`anthropic`/`mcp` 等大依赖，冷启动通常需数秒；测试在子进程打开数据库前就超时，`tearDown` 随即删除 `TemporaryDirectory`，子进程随后启动时路径已不存在，表现为 `unable to open database file`。不是「spawn 无法打开 SQLite」的普遍限制——最小探针（父进程保持 WAL 连接 + spawn 子进程打开同一临时 SQLite、以及完整 ExecutionStore 模拟）均可成功。

修复：`gateway/mcp/tests/test_gateway.py` 的 `wait_for` 超时从 2 秒放宽到 15 秒，覆盖 Windows spawn 冷启动。修复后 5 项测试全部通过（`Ran 5 tests ... OK`，12.8s）。

**建议 1 已闭合**：3 项失败可复现，已归因（Cold-start spawn 慢于测试超时）并修复测试超时；`ai4-xejt` 的「5 passed」证据在当时环境可复现，旧记录标注验证环境为当时执行时的本机。测试超时属测试基准问题，非 `ai4-z3z4` 行为验收改动。

## 事实二：看板 Gateway/消息监听来源契约缺口

`ai4-lrfz` 的 `dashboard-api` 已实现聚合与安全降级，但 Gateway 与消息监听两个来源因缺少稳定只读查询契约而无法配置，只能以 `unavailable/partial` 呈现。已存在的 Gitee issue `IKPT5I`（2026-10-23，作者 hanjiang-215）已列出所需只读能力与约束，本票不重复正文。**截至 2026-10-25，`IKPT5I` 仍 open，尚无 Centre Agent/消息监听侧的确定进展；该契约依赖 `ai4-te1v` 消息语义收敛后的订阅器实现，保持待办。**

## 建议

1. ~~Centre Agent 侧在本机复跑上述 3 项测试确认失败是否可复现；若为 Windows 特有，补充跨平台说明或修复临时路径/子进程生命周期~~ — 已复现并修复（事实一），测试 `wait_for` 超时放宽为 Windows spawn 冷启动预留时间。
2. 若 gateway/mcp 测试修复涉及 `ai4-z3z4` 的验收标准「全部测试决策所列行为均有自动化验证」，请该票负责人裁决是否补充 Windows 环境的测试边界 — 本修复只改测试超时，不改行为；`ai4-z3z4` 负责人（hanjiang）裁决无需追加 Windows 专项，等待超时已在单测内体现。
3. `IKPT5I` 的契约确认进展与 `ai4-lrfz` 的 Gateway/消息监听来源配置保持同步；`ai4-lrfz` 侧在契约就绪前维持 `unavailable/partial` 降级 — 契约依赖 `ai4-te1v`，继续待办并记录在事实二。

## Acceptance Criteria

- [x] Centre Agent 侧确认 3 项失败是否可复现，并给出归因或修复；`ai4-xejt` 验证证据标注运行环境
- [ ] `IKPT5I` 或等价渠道给出 Gateway/消息监听只读契约的确定进展（依赖 ai4-te1v，待办）
- [x] 本票结案时记录裁决结论与证据，不留下未验证断言

## Notes

**2026-10-25 归因与修复（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

复现失败后做二分定位：最小 spawn 探针（父进程保持 WAL 连接、spawn 子进程打开同一临时 SQLite）成功，`ExecutionStore` 完整模拟也成功，证明不是 spawn 无法打开 SQLite 的普遍限制。随后发现 `_probe_module` 探针（`wait_for` 3 秒）通过、`_probe_minimal` 探针（`wait_for` 2 秒）失败，子进程打印 `exists=False` —— 确认根因是 **Windows + Python 3.14 下 spawn 子进程冷启动耗时超过测试 `wait_for` 的 2 秒超时**：子进程需重新 import `openai`/`anthropic`/`mcp` 等大依赖，冷启动通常数秒；测试超时后 `tearDown` 删除 `TemporaryDirectory`，子进程随后打开路径时报 `unable to open database file`。

修复：`gateway/mcp/tests/test_gateway.py` 的 `wait_for` 超时由 2 秒放宽到 15 秒。验证：`uv run --locked --package sciweave-task-agent-gateway-mcp python -m unittest discover -s gateway/mcp/tests -v`，5 项全部通过（`Ran 5 tests ... OK`，12.8s）。`ai4-xejt` 的「5 passed」记录在对应环境可复现；旧记录未标注 Windows spawn 冷启动成本，本次已归因。

事实二（看板 Gateway/消息监听契约）仍依赖 `ai4-te1v`（Frank Qi）消息语义收敛，`IKPT5I` 保持 open 待办。

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。

**2026-10-23T12:45:00Z**

由 hanjiang 在 `feature/hanjiang` 上审查时发现并记录。依据仓库 ticket 属人规则，本票不改写 Frank Qi 名下 `ai4-z3z4`/`ai4-xejt` 的内容，只作为关联票承载事实与建议。复跑命令与失败签名见上方「事实一」。

**2026-10-23T12:50:00Z**

已向 Gitee 提 issue 通知 Frank Qi：[请 Frank Qi 确认：Centre Agent gateway/mcp 测试复跑失败与看板 Gateway 来源缺口](https://gitee.com/qi-yueran/ai4science/issues/IKQ2KK)，正文首行 @Frank Qi 并列出两项事实、复现命令、失败签名、对照证据与最小复现结论。
