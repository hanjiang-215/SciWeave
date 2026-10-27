---
id: ai4-0fwc
status: closed
deps: []
links: [ai4-58d0, ai4-g1km, ai4-z3z4, ai4-8aa0]
created: 2026-10-27T12:57:11Z
type: bug
priority: 1
assignee: Frank Qi
tags: [toolkit, task-agent, runtime, wiring]
---
# 订阅端从不调用模型：worker 执行壳没有任何调用方

套件的两条执行路径里，**带模型的那一条没有被接上**。`service-template/worker/src/main.py` 会调 `build_agent_runtime()` 与 `run_queued_once()`，但全树没有任何代码启动这个入口、也没有任何代码 import 它。真正被常驻起来的 `bin/start-subscriber` 走的是另一条路径。

## 一、实测：常驻订阅端跑完一轮，草稿 payload 是拼出来的字符串

用套件自带的假队列向 subscriber 投一条正常交接，环境变量全部照 `.env.example`：

```
messages processed: 1
execution status : completed
draft payload    : '':evt-1'
```

`completed` 是真的，`draft` 也是真的（`FakeDraftBox` 返回了 `draft-node-1-xxxx`），但**没有任何模型被调用**。payload 来自 `runtime.py` 的 `run_one()`：

```python
draft_id = drafts.write(target_id=target_id, payload=f"{agent_definition}:{event_id}")
```

`agent_definition` 在 subscriber 的调用点没有传（`subscriber/src/main.py` 的 `runtime.handle_inbound(str(target_id), event_id)` 只传两个参数），所以它就是空串，于是 payload 变成 `':evt-1'`。

## 二、带模型的那条路径没有调用方

```
$ grep -rn "run_queued_once" --include=*.py . | grep -v tests/
service-template/worker/src/main.py:23:from work_agent_runtime.worker_shell import run_queued_once
service-template/worker/src/main.py:56:    results = run_queued_once(runtime, agent, limit=limit)

$ grep -rn "subprocess|Popen" --include=*.py runtime/src service-template
（无命中）
```

`worker/src/main.py` 只被它自己引用。`bin/start-subscriber` 与 `bin/start-mcp` 都不碰它，systemd 也没有第三个 unit。所以：

- `run_queued_once()` —— 唯一调用 `agent.run(request)` 的地方 —— 只在 `runtime/tests/test_worker_shell.py` 里被执行过；
- `build_agent_runtime()`（`ai4-g1km` 交付的真实 fast-agent 装配）除了 `worker/src/main.py:56` 之外**没有任何生产调用方**；
- 结论：`ai4-g1km` 把运行时写对了、测过了，但它接在一个没人启动的进程里。

`ai4-8aa0` 的重开备注里记了这条，本票是它的可执行化。

## 三、这不是「少写一行」

`run_one()` 和 `run_queued_once()` 是两套不同的状态机，接哪一条要先定：

| | `run_one()`（subscriber 现在走的） | `run_queued_once()`（worker 的） |
| --- | --- | --- |
| 谁执行 | subscriber 进程内联 | 一次性 worker 进程 |
| 草稿 payload | `f"{agent_definition}:{event_id}"` | `outcome.result_summary`（模型产出） |
| 模型调用 | 无 | `agent.run(request)` |
| 租约 | `WorkerLease.acquire()` | 无（靠 inbox 行状态互斥） |
| 失败后 | 行保持 `queued`，可 replay | 行保持 `queued`，可 replay |
| `mark_processed` | `handle_inbound` 里 | `run_queued_once` 里 |

按 ADR-0002 与 `docs/data-flow/work-agent.md`，Worker 是**短生命周期子进程**，subscriber 负责拉起来。所以正确形状是「subscriber 处理消息 → 取得租约 → 拉起 worker 子进程 → worker 跑完写草稿 → subscriber 提交 offset」，而不是让 subscriber 内联调模型（那会让常驻进程持有模型凭据与长任务）。

但**本票不先定这个**：ADR 说子进程，代码里 `WorkerLease` 在 subscriber 进程内，`run_queued_once` 又自己不看租约——三者对不上，属于设计裁决，见 Not in Scope。

## Design

**裁决（用户 2026-10-27）：按 ADR-0002 —— subscriber 拉子进程，租约改成 SQLite 持久锁。**

### 1. 谁拉起 worker

`runtime/src/work_agent_runtime/worker_dispatch.py` 的 `WorkerSubprocess`：subscriber 拿到交接后 `subprocess.run([...main.py, "--dedupe-key", key])`，等它结束，读它 stdout 最后一行的 JSON 拿 `draft_id`。默认命令是 `[sys.executable, <kit>/service-template/worker/src/main.py]`，不用 `uv run` —— subscriber 本来就跑在 runtime 的环境里，每条消息再走一次 uv 只是白付一次 lock 检查。`SCIWEAVE_WORKER_COMMAND` 可覆盖（JSON 数组或空白分隔字符串）。

`WorkAgentRuntime` 新增 `dispatcher` 参数：一个接受 `dedupe_key` 的可调用对象，返回带 `status`/`draft_id` 的结果。有它就走子进程，没有就仍走 `run_one()` 内联。这不是两条实现，是一条缝：内联路径留给没有 `DATABASE_PATH` 的内存演示，`build_runtime()` 会打印一行说明它选了哪条。

### 2. 租约：从 `threading.Lock` 到 SQLite 一行

`WorkerLease` 移到 `lease.py`，`runtime.py` 里保留 re-export（大量既有 import 不必改）。两种形态：

| 构造 | 后端 | 用在哪 |
| --- | --- | --- |
| `WorkerLease()` | 进程内 `set` | 单测、内存演示 |
| `WorkerLease(path)` | `worker_lease` 表 | 真实路径，与 inbox 同一个 SQLite 文件 |

`acquire` 用 `BEGIN IMMEDIATE` 先拿写锁再读，两个进程不可能都读到「空闲」再都写进去。租约带 TTL（默认 1800 秒）：被 `kill -9` 的 subscriber 不会永久占住一个节点。**同一 owner 二次 acquire 也返回 False**——否则同一 subscriber 内的第二次投递会静默续租并拉起第二个 worker，而那条路径正是租约存在的理由；要续租用显式的 `renew()`。代价是模型调用超过 TTL 时租约会被别的进程接手，所以 TTL 给得宽，且过期只被解释为「上一个 owner 已经没了」，不做抢占。

### 3. offset 在 worker 开始跑之前就提交

这是本票唯一一处改变语义的地方，写在这里而不是埋在代码注释里。把 offset 押到模型返回，重启后整批消息重放、而 inbox 去重又把它们全挡掉——比丢一条更糟。现在的规则是「inbox 行落盘即提交」：崩溃只会留下一条 `queued` 行，`drain_queued()` 下次启动时重跑。`run_loop` 原本就是这个形状，本票只是把「落盘」的定义从「执行完」改成「入队完」，并加了测试钉住。

### 4. worker 侧只认一个 key

`worker_shell.run_one_queued(runtime, agent, dedupe_key)`：只跑指定的那一行，不扫 `queued`。让 worker 自己扫会和另一个 subscriber 抢同一行。`run_queued_once()` 保留为批量形态，给没有 `--dedupe-key` 的一次性启动用。

`not_found` / `already_processed` 不是失败，退出码 0：subscriber 先提交再派发，重放时撞上一条已完成的、或已被别的 worker 拿走的行，是正常竞态，不是错误。

## Acceptance Criteria

- [x] 新增测试：向 subscriber 投一条交接消息后，断言 subscriber 侧**不写任何草稿**（`runtime.drafts.write` 被调用即 fail），且 worker 子进程把行标成 `processed`。见 `test_worker_dispatch.py::DispatcherTests::test_the_inline_draft_write_never_happens_on_the_dispatch_path` 与 `test_subscriber_loop.py::SubscriberDispatchTests::test_a_real_handoff_through_the_subscriber_starts_the_worker`。
- [x] 新增测试：worker 入口在生产代码里有调用方，且是**真子进程**。见 `ShippedWorkerEntryPointTests`（跑真实的 `service-template/worker/src/main.py`）与 `SubscriberDispatchTests::test_a_real_handoff_through_the_subscriber_starts_the_worker`（消息 → inbox → 子进程 → `processed`）。
- [x] README 与 `deploy-task-agent-skills/verify-task-agent/references/e2e-checklist.md` 不再宣称「假上游交接 → 多 Agent 工作流 → 唯一 draft_id」这条链路已成立：README 新增「一次交接的完整路径」一节，checklist 改成逐条可核对的表格，并**明确列出三项未成立**（真实模型产出、多 Agent 工作流、任务文本）。
- [x] `DRAFT_BUFFER_MCP_TOKEN` 只在 worker 侧读取：`test_subscriber_loop.py::SubscriberDraftBoundaryTests::test_the_subscriber_module_does_not_import_the_draft_writer` 仍然通过。
- [x] 新增测试：租约**跨进程**有效。见 `test_worker_dispatch.py::LeaseAcrossProcessesTests`（另起一个 Python 进程抢同一个 target）。

## Not in Scope

- 不改 `fast_agent_runtime.py` 的实现（`ai4-g1km` 的成果）。
- 不改 `run_one()` 的签名与 `handle_message` 的兼容路径（内联路径仍在，只是有 `DATABASE_PATH` 时不走它）。
- 不实现 `ai4-x0ay` 的 `mcp.servers` 翻译。
- **不接工作流**：worker 现在跑单个 agent，`WorkflowExecutor` 已测但未接线（`ai4-x0ay`）。
- **不改任务文本**：`command_text` 仍是裸 node id，payload 在写行时就丢了（`ai4-1e9e`，`deps: [ai4-0fwc]`）。

## Notes

**2026-10-27 立项（Frank Qi）**

> *This was generated by AI during triage.*

身份核对：assignee `Frank Qi`、分支 `feature/frank-qi`、`git config user.name=Frank Qi`，三者一致。

立项依据全部是本机实测，不是读代码推断：用 `.env.example` 填环境后向 subscriber 投一条 `{"target": {"id": "node-1"}, "event_id": "evt-1"}`，`run_loop` 返回 1、执行记录 `completed`、`FakeDraftBox` 收到 payload，实测值为 `':evt-1'`。`run_queued_once` 与 `build_agent_runtime` 的调用方是用 `grep -rn` 在 `runtime/src` 与 `service-template` 全树核实的。

与 `ai4-58d0` 不重复：那张票修的是「草稿写入器接口不一致」与「`mark_processed` 位置错误」，`run_one()` 的 payload 拼接形状不是它的范围。

与 `ai4-g1km` 不重复：那张票交付的是运行时实现本身，它的验收第 3 条写的是「worker 的 `main.py` 在配置齐全时走真实运行时」——`main.py` 确实走真实运行时了，但它没人启动。本票补的正是这条边界。

与 `ai4-4zjz` 不重复：那张票只移动了草稿箱凭据的**位置**（从 subscriber 移到 worker），没有处理「worker 根本没被启动」。

**2026-10-27 裁决与实现（Frank Qi）**

> *This was generated by AI during triage.*

身份核对：assignee `Frank Qi`、分支 `feature/frank-qi`、`git config user.name=Frank Qi`，三者一致。

用户裁决「按 ADR-0002：subscriber 拉子进程，租约改成 SQLite 持久锁」，Design 与验收标准已按该裁决重写，原「待定」段已删除（本票从未发出，未造成外部依赖）。

实测证据（本机）：

```
# 手动跑完整链路，worker 是独立进程
record: ExecutionRecord(target_id='node-1', status='completed', draft_id='draft-node-1-50e057d3')
inbox row: {... 'status': 'processed'}
lease holder after: None
```

改动清单：

- 新 `runtime/src/work_agent_runtime/lease.py`：SQLite 租约（`acquire`/`renew`/`release`/`holder`/`reap`），`WorkerLease()` 无参仍是内存形态。
- 新 `runtime/src/work_agent_runtime/worker_dispatch.py`：`WorkerSubprocess`（可调用）、`WorkerRun`、`default_command()`、`_draft_id_from()`。
- `runtime.py`：`WorkAgentRuntime(dispatcher=...)`，新增 `_dispatch()`；`WorkerLease` 改为 re-export。
- `worker_shell.py`：新增 `run_one_queued(runtime, agent, dedupe_key)`；`run_queued_once()` 改成对它的循环。
- `service-template/worker/src/main.py`：认 `--dedupe-key`；`not_found`/`already_processed` 退出码为 0。
- `service-template/gateway/subscriber/src/main.py`：`build_runtime()` 接租约与 dispatcher，`SCIWEAVE_WORKER_DISPATCH=0` 可关；没有 `DATABASE_PATH` 时打印降级说明。
- `.env.example`：`SCIWEAVE_WORKER_DISPATCH`、`SCIWEAVE_WORKER_COMMAND`、`SCIWEAVE_WORKER_TIMEOUT_SECONDS`。
- README：新增「一次交接的完整路径」。
- `.tickets/ai4-1e9e.md`：新票，接在本票后面处理任务文本。

验证：`cd runtime && uv run python -m unittest discover -s tests` → **235 tests OK**（本票前 202）。

一个被推翻的初版设计记录在这里，避免以后有人「优化」回去：最初让同一 owner 二次 `acquire` 续租。测试 `test_a_second_acquire_is_also_refused_not_renewed` 说明为什么不行——同一 subscriber 里的第二次投递会静默续租并拉起第二个 worker，而那正是租约要拦的情况。需要续租时用显式的 `renew()`。

