# Work Agent：两种实例的统一架构

Task Agent 与 Centre Agent 共用一个架构。二者只在三处不同：订阅什么、一轮 loop 干什么、MCP 处置面承接什么动作。存储、进程角色、状态机与失败处置一律相同。

本文取代 `task-agent-binding.md` 里「中央部署」的形态描述，也是「最小 Work Agent 实现规格」(ai4-z3z4) 与「中央 Agent 候选预审职能地图」(ai4-fv1r) 的形态依据。

## 术语位置

`Work Agent` 是上位词，不是替代词。已有的票、代码与文档继续使用 `Task Agent` 与 `Centre Agent` 两个实例名，不批量改名。

| 名字 | 指什么 | 部署位置 |
| --- | --- | --- |
| Work Agent | 统一架构的上位词 | — |
| Task Agent | 执行科研任务的 Work Agent 实例 | 研究员本机 |
| Centre Agent | 做候选预审的 Work Agent 实例 | 中央服务器 |

源码分两份，架构仍是这一套。Centre Agent 在 `sci-weave/centre-control/centre-agents`，Task Agent 发给研究员的套件在 `sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent`。两边不 path 依赖；状态机、Worker Lease 和处置面以「最小 Work Agent 实现规格」为准。详见 [ADR-0002](../adr/0002-work-agent-two-codebases.md)。

## 三个组件

一个 Work Agent 是一个项目组，含三个独立 Python 子项目：

| 组件 | 职责 | 生命周期 |
| --- | --- | --- |
| `gateway/mcp` | 返修与处置面，MCP Streamable HTTP，只服务本机 Operator | 常驻 |
| `gateway/subscriber` | 消息监听：出站连接中央队列，按 `task_node_id`（Task Agent）或候选事件（Centre Agent）订阅 | 常驻 |
| `worker` | 一轮 fast-agent-mcp loop，结束即退出 | 短生命周期 |

`gateway` 指 `mcp` 与 `subscriber` 的复合，不是一个独立进程。二者不共享 Python 代码，但共享同一个 SQLite 文件与同一套状态机，共同构成 Worker 的唯一启动与串行化边界。组件组外的客户端与消费者不得启动 Worker。

消息监听是出站连接，端侧不需要公网可达地址。订阅器的价值在于长期持有 consumer group 与 offset：把消息监听并进 MCP 进程，会让 MCP 的生命周期绑上队列连接，任何一侧重启都牵连另一侧。

消息队列从正式版本发布到下游执行的完整交接流程见 [`message-queue.md`](message-queue.md)。该流程区分下游通知、`PendingHandoff` 等待事实和真正触发 Worker 的 `task_handoff_ready`；队列不阻塞等待下游正式化。

## 消息进入路径

一条消息到达后，订阅器做四件事，顺序固定：

1. 按消息里的 `task_node_id` 取该节点的稳定 `session_id`（Task Agent），或取候选目标（Centre Agent）。
2. 在单个 SQLite 事务里创建一条 `queued` ExecutionRecord，`trigger=queue`，`trigger_ref` 记为消息标识，并写审计事件。
3. 尝试原子领取该目标的 Worker Lease；领到才启动 `worker`。
4. 报告写完后才提交 consumer offset；重放靠业务键幂等挡住，不靠 offset 精确一次。

**没有 `blocked` 状态。** 消息能到达，就说明上游正式版本已经发布——这是队列承载的证明，Gateway 不需要再猜一次。Gateway 在本地再判一次「上游就绪」只会制造第二份可能与正式版本不一致的判断。

## 执行记录

ExecutionRecord 是唯一的 Gateway 状态机，一轮 loop 一条记录。

```text
queued → running
running ├→ waiting              （Worker 提问，本轮终止；回答创建 resume_of 新记录）
        ├→ completed            （草稿已写入中央草稿箱，记录保存 draft_id）
        ├→ needs_revision       （处置面要求返修，创建 revision_of 新记录）
        ├→ rejected             （处置面放弃这一轮，终态）
        ├→ human_takeover       （处置面转人工，终态）
        ├→ failed               （运行时异常、超时、非零退出、会话恢复失败、草稿写入失败）
        └→ cancelled
```

**没有 `awaiting_acceptance`，也没有 `accepted`。** 一审不在 Gateway 里发生：agent 把结果写成草稿，研究员用自己的 Codex 审阅，把该草稿作为候选分支提交即表示一审通过。Gateway 若再存一份「已接纳」，就是一条查不到真实进度的本地投影，会让人误以为在 Gateway 里能看到审核结果。

`completed` 是正常终点。它说明 Gateway 已知的事实到此为止：一轮 loop 跑完了，草稿号是多少。草稿之后被审、被转候选还是被丢弃，属于草稿箱与领域治理，Gateway 不投影。

草稿写入失败记为 `failed`，错误码 `draft_submission_failed`，不自动重写、不自动重跑。原始结果随 Worker 进程退出而消失，让研究员重跑一轮比让 Gateway 假装还能恢复它更诚实。

## 草稿写入

写草稿的不是 Gateway，是跑在 Worker 里的 agent 本身。中央草稿箱的 MCP 作为工具注册给该 Work Agent，agent 在 loop 末尾自行调用 `create_draft`。

因此 Gateway 不持有草稿箱凭据，也不需要知道领域命名空间的审核人。它只从 agent 拿回一个 `draft_id` 写进 `completed` 记录。

这条边界同时决定了权限模型：草稿箱知道「谁提交了什么」，Gateway 知道「哪一轮执行产出了它」。二者靠 `draft_id` 与 `execution_id` 双向弱引用，不共享存储。

## MCP 处置面

`gateway/mcp` 只承接人要做的事，不承接任务下发：

| 工具 | 用途 |
| --- | --- |
| `query_execution(execution_id)` | 查执行状态、会话、结果摘要、待答问题、trigger |
| `list_pending(task_node_id?)` | 列出 needs_revision、waiting、running 等需人介入的记录 |
| `cancel_execution(execution_id)` | 取消未终结执行，幂等 |
| `answer_question(execution_id, answer, idempotency_key)` | 回答 Worker 提问，创建 `resume_of` 新记录 |
| `review_execution(execution_id, decision, reason, idempotency_key)` | `request_revision` / `reject` / `request_human_takeover` |
| `health()` | 聚合 SQLite、队列、Worker runtime 与调度器状态 |

**没有 `submit_owner_command`。** 任务下发只走消息队列；留一个能创建新执行的工具，等于给「MCP 只做返修」留一道后门。根任务的首条消息由 Project Owner 触发，上游交接由正式版本发布触发，两者都不是 MCP 调用。

`review_execution` 没有 `accept` 分支。认可结果的动作是「把草稿转成候选」，发生在研究员的 Codex 与领域管理 MCP 之间。

业务错误码：`not_found`、`invalid_state`、`unavailable`、`unimplemented`、`internal`。错误不得包含令牌、异常、堆栈、文件路径或原始命令。

## 研究员侧处置面的当前契约

`sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent` 的研究员自有处置面提供同名六个工具，但只覆盖「这一个研究员的执行记录」，因此签名比中央侧简单，差异如下：

| 工具 | 研究员侧当前签名 | 与上表的差异 |
| --- | --- | --- |
| `query_execution(execution_id)` | 同 | 返回状态、草稿 id、错误码、失败 Agent 与已记录的审核决定 |
| `list_pending()` | 无参数 | 只列 `queued`/`running`/`waiting`，不支持按 task_node 过滤 |
| `cancel_execution(execution_id)` | 同 | 终态执行拒绝取消并回 `invalid_transition` |
| `answer_question(question_id, answer)` | 按问题 id | 不创建 `resume_of` 新记录，回答后原地回到 `queued`；无 `idempotency_key` |
| `review_execution(execution_id, decision, reason)` | 两分支 | 只有 `accepted`/`rejected`，追加不覆盖；无 `request_revision`/`request_human_takeover` 与幂等键 |
| `health()` | 同 | 返回 `ready` 与 pending 计数 |

补齐幂等键与 `resume_of` 链需要先定研究员侧的重新入队语义，见 `ai4-58d0` 的备注；在那之前两侧契约有意不同，不要按中央侧签名去调用研究员侧工具。

## Centre Agent 的差异

结构与 Task Agent 完全一致，三处不同：

| 项 | Task Agent | Centre Agent |
| --- | --- | --- |
| 订阅目标 | 自己负责的 `task_node_id` | 候选创建与候选头更新事件；正式版本发布事件 |
| 一轮 loop 做什么 | 执行科研任务，产出草稿 | 拉全量候选快照做预审，追加报告；必要时新建混合候选 |
| 处置面承接什么 | 返修、放弃、转人工、回答提问 | 列出待审候选、查看报告、要求重算某候选的报告 |

处置面的工具名与签名保持一致，但 Centre Agent 目前不提供功能：它的工作里没有返修。保留同名接口是为了让两个实例共用一套骨架，返回 `unimplemented`，而不是让 Centre Agent 长出一个自己的工具面。

Worker Lease 在两种实例里都保留，定位是**本地单实例互斥**：同一目标同时只跑一轮，重复投递由本地的唯一约束挡住。它不是跨实例的分发租约，中央仍然只有一个 Centre Agent 实例。

## 配置

路径、地址、端口、令牌、队列地址、数据库位置与 Worker 持久目录全部来自环境变量，仓库只提交 `.env.example`。Task Agent 与 Centre Agent 各自维护自己的 `.env`，互不共享凭据。

## 不做的事

- 不部署、不安装、不重启、不托管研究员本机的 Task Agent。
- 不写正式版本，不改写已有候选，不写草稿的接纳状态。
- 不替 Project Owner 做批准，不判断「下一步该谁动」。
- 不写审计。留痕由中央 MCP 接口层统一记录对外调用；领域治理记录由领域服务自己写，两者作用域分开。
- 不在 MCP 面上承接任务下发。
