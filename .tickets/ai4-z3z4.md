---
id: ai4-z3z4
status: open
deps: []
links: [ai4-yyy9, ai4-dhpv, ai4-we38, ai4-za77, ai4-fv1r]
created: 2026-10-19T07:07:36Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [spec, work-agent, task-agent, fast-agent, ready-for-agent]
---
# 最小 Work Agent 实现规格

> **改写（2026-10-22）：本票已按端侧自持与 Work Agent 统一架构重写。** 原名《最小 Task Agent 项目组实现规格》，原正文描述的「中央项目组、中央 Gateway 拉起 Worker、Owner 命令下发」形态已作废。现行形态依据 [`docs/data-flow/work-agent.md`](../../docs/data-flow/work-agent.md) 与 [ADR-0001](../../docs/adr/0001-task-dispatch-via-message-queue.md)。重写要点见文末 Notes 的 2026-10-22 条。

将 Work Agent 的统一架构收敛为一个可交付的实现规格：三个组件、一份本地 SQLite、一套 Execution Record 状态机、一个只承接处置的 MCP 面。Task Agent 与 Centre Agent 共用本架构，本规格以 Task Agent 为主要实例描述，Centre Agent 的差异在独立一节列出。

这是后续 Work Agent 实现 tickets 的唯一上游输入。

## Problem Statement

研究员需要在自己电脑上运行一个能接活的 Agent：收到上游交接就执行，执行中能被自己追问、取消、要求返修，执行完把结果写成草稿交给人审。中央需要同样结构的一个 Agent 做候选预审。

现状是 `sci-weave/task-agent` 有一个 HTTP/SQLite 的 Gateway MVP、一个 `ingest` 空骨架和一个 Worker 骨架，形态仍按「中央部署、MCP 下发任务」写。三处已失效：位置（中央改端侧）、下发通道（MCP 改消息队列）、结果去处（Gateway SQLite 改中央草稿箱）。

## Solution

一个 Work Agent 是一个项目组，三个独立 Python 子项目：

- `gateway/mcp`：返修与处置面，MCP Streamable HTTP，只服务本机 Operator，常驻。
- `gateway/subscriber`：消息监听，出站连接中央队列，常驻。
- `worker`：一轮 fast-agent-mcp loop，结束即退出。

`gateway` 是前两个组件的复合名，不是一个进程。三者共享一份本地 SQLite 与一套状态机；`mcp` 与 `subscriber` 共同构成 Worker 的唯一启动与串行化边界。

消息到达 → 创建 `queued` 执行记录 → 原子领取 Worker Lease → 拉起 Worker → loop 结束把草稿写进中央草稿箱 → 记为 `completed` 并保存 `draft_id`。

## User Stories

1. 作为 Task Owner，我希望 Agent 收到上游交接就自动开工，以便调度不依赖我保持某个客户端在线。
2. 作为 Task Owner，我希望提交后能查询执行的状态、会话、结果摘要、错误摘要和待答问题，以便恢复工作上下文。
3. 作为 Task Owner，我希望列出需要我介入的执行，以便发现正在等我回答、等我返修或正在运行的记录。
4. 作为 Task Owner，我希望取消未终结的执行，以便停止不再需要的工作；重复取消或已终结执行可安全得到未接受取消的结果。
5. 作为 Task Owner，我希望回答 Worker 的提问后以同一稳定会话启动新的恢复执行，以便不依赖旧进程仍存活。
6. 作为 Task Owner，我希望要求返修、放弃这一轮或转人工，以便把不满意的结果处置掉。
7. 作为 Agent 的编写者，我希望 Agent 在 loop 末尾把结果写成中央草稿箱的草稿，以便研究员在自己的 Codex 里审阅后直接把它转成候选分支。
8. 作为本地开发者，我希望未携带正确令牌的请求在进入 MCP 工具前被拒绝，以便不会污染执行事实与审计链。
9. 作为本地开发者，我希望已认证请求以配置的 Caller 记录，以便审计能说明请求来源，但不伪装为已具备 TaskNode 授权。
10. 作为订阅器维护者，我希望重复投递的消息不会产生第二轮执行，以便至少一次投递不会重复消耗模型额度。
11. 作为订阅器维护者，我希望同一订阅目标同时只有一个 Worker 在跑，以便不会并发写出两份互相矛盾的草稿。
12. 作为订阅器维护者，我希望不同 TaskNode 可以并发执行，以便不把全局吞吐量限制成单 Worker。
13. 作为订阅器维护者，我希望执行完再提交 consumer offset，以便进程崩溃后消息不被吞掉。
14. 作为 Worker，我希望获得稳定 session_id、持久 home、connection scope 和 session history，以便新的短生命周期进程能够恢复会话。
15. 作为 Worker，我希望每次完成、暂停或失败后退出，以便 Gateway 保持为常驻控制面而非长期占用执行进程。
16. 作为维护者，我希望运行时异常、超时、非零退出、会话恢复失败和草稿写入失败都被记为 failed，以便故障可查询且不自动重做。
17. 作为维护者，我希望健康信息聚合 SQLite、队列连接、Worker runtime 与调度器的实际可用性，以便诊断配置缺失、降级和不可用状态。
18. 作为本地探针，我希望无需 MCP 令牌取得最小健康状态和 API 版本，以便检测服务存活而不暴露内部组件详情。
19. 作为 Centre Agent 的维护者，我希望它与 Task Agent 共用同一套骨架与工具签名，以便两个实例只有配置和提示词不同，不需要维护两套状态机。
20. 作为实现者，我希望对外测试只经 MCP 工具和最小 HTTP 探针验证，以便实现可在不破坏客户端行为的前提下重构。

## Implementation Decisions

### 项目组与进程边界

- Work Agent 是一个项目组，含 `gateway/mcp`、`gateway/subscriber`、`worker` 三个独立 Python 子项目，共用项目组级 uv workspace、锁文件与跨角色环境配置。
- `gateway/mcp` 是常驻 MCP Server；`gateway/subscriber` 是常驻队列消费者；`worker` 是一次 loop 一个进程的短生命周期角色。
- `mcp` 与 `subscriber` 不共享 Python 代码，但共享同一个 SQLite 文件。二者加上共享持久化契约，是唯一可启动 Worker 并裁决同目标串行化的边界；组件组外客户端与消费者不得启动 Worker。
- 共享 SQLite 持久化包提供 schema、幂等 bootstrap、受约束表访问、状态迁移校验、Worker Lease、审计与健康读写；不包含 MCP、队列或 Worker 业务。
- 首版只需要幂等 bootstrap；已有数据库的结构升级另行设计 migration。

### 消息进入路径

- 订阅器订阅自己的目标：Task Agent 按 `task_node_id`，Centre Agent 按候选事件与正式版本发布事件。
- 一条消息到达后，在一个 SQLite 事务里创建 `queued` ExecutionRecord（`trigger=queue`，`trigger_ref` 记消息标识）并写审计事件；随后原子领取该目标的 Worker Lease，领到才拉起 `worker`。
- **没有 `blocked` 状态。** 消息能到达即证明上游正式版本已发布，Gateway 不重复判断上游是否就绪。
- 去重靠业务键（`task_node_id` + 触发版本标识）的唯一约束，不靠队列精确一次投递。
- offset 在整轮执行完结后提交；崩溃重启会重放，重复由业务键挡住。

### Owner MCP v1 协议（处置面）

- 采用 MCP Streamable HTTP；不用 stdio，因为客户端进程生命周期不能承载常驻 Gateway 的持久调度职责；不用 A2A，因为它不是 Operator harness 的既定扩展面。
- MCP 初始化承担协议版本协商；认证后的 `health` 返回 `work_agent_api_version: "v1"`。v1 只能兼容性新增可选字段或工具；删字段、收紧字段或改变既有语义时升主版本。
- 所有成功工具结果仅在 MCP `content` 中返回一个 JSON 文本对象；不声明 `outputSchema`，不返回 `structuredContent`。
- 无效 JSON-RPC、未知工具、缺失必填参数和类型不符由 MCP/JSON-RPC 协议错误表达。通过参数校验后进入工具的业务失败以 `isError: true` 返回 JSON 文本 `{ "error": { "code", "message" } }`。
- 业务错误码：`not_found`、`invalid_state`、`unavailable`、`unimplemented`、`internal`。错误不得包含令牌、异常、堆栈、文件路径或原始命令。
- 工具清单：
  - `query_execution(execution_id)` 返回执行、任务、会话、稳定状态、结果/错误摘要、待答问题、`draft_id`、`trigger` 和 `trigger_ref`；不存在时 `not_found`。
  - `list_pending(task_node_id?)` 一次返回 `waiting`、`needs_revision`、`running` 的记录，按 `created_at`、`execution_id` 升序；首版不分页。
  - `cancel_execution(execution_id)` 对存在的执行总返回 execution_id、execution_status 和 accepted。accepted 仅表示本次取消请求被接受；已终结、人工接管或已取消时为 false。不存在时 `not_found`。
  - `answer_question(execution_id, answer, idempotency_key)` 对 `waiting` 记录创建 `resume_of` 关联的新记录。
  - `review_execution(execution_id, decision, reason, idempotency_key)` 支持 `request_revision`、`reject`、`request_human_takeover`；返回处置后的状态、可选后继执行标识和 duplicate。
  - `health()` 返回聚合状态与 MCP、队列、Worker runtime、存储、调度器分项状态。
- **没有 `submit_owner_command`，`review_execution` 也没有 `accept`。** 任务下发只走消息队列；认可结果的动作是研究员在自己的 Codex 里把草稿转成候选分支，那是领域管理 MCP 的事，不是本处置面的事。
- 幂等键仅在各自工具内全局唯一；重复键返回首次持久化结果并标记 `duplicate=true`，不比较后续参数。
- 回环 HTTP 健康探针不要求令牌，只返回 `status` 和 `work_agent_api_version`；与认证 `health` 复用一套健康计算。

### 身份、配置与健康

- 每个 MCP HTTP 请求均需 `Authorization: Bearer <token>`；令牌与 `caller_id` 均由环境变量提供。校验成功后写入审计事件的操作者。
- 缺失或无效令牌返回 HTTP 401，不创建任何执行事实或审计事件。首版不实现 OAuth、scope、多人身份或 TaskNode Owner 授权绑定。
- 所有部署路径、监听地址、端口、令牌、数据库位置、Worker 持久目录、队列地址与草稿箱地址均由环境变量配置；仓库只保留变量示例。
- SQLite 可读写且 schema 兼容是核心条件；核心存储故障为 `unavailable`。已配置的必需组件故障为 `degraded`，未配置组件为 `not_configured`，全部满足为 `ready`。

### 持久化与状态机

- TaskSession 为每个订阅目标持有稳定 `session_id`；它是会话投影，不替代 ExecutionRecord 的审计事实。
- ExecutionRecord 是唯一的工作流状态机，一次可追踪执行尝试一条。

```text
queued → running
running ├→ waiting            （Worker 提问，本轮终止；回答创建 resume_of 新记录）
        ├→ completed          （草稿已写入中央草稿箱，记录保存 draft_id）
        ├→ needs_revision     （处置面要求返修，创建 revision_of 新记录）
        ├→ rejected           （处置面放弃这一轮，终态）
        ├→ human_takeover     （处置面转人工，终态）
        ├→ failed             （运行时异常、超时、非零退出、会话恢复失败、草稿写入失败）
        └→ cancelled
```

- **没有 `awaiting_acceptance` 与 `accepted`。** 一审在中央草稿箱发生：研究员审阅草稿后把它作为候选分支提交即表示通过。Gateway 若再存一份接纳状态，就是一条查不到真实进度的本地投影。
- `completed` 是正常终点，说明 Gateway 已知的事实到此为止：一轮 loop 跑完了，草稿号是多少。草稿之后被审、被转候选还是被丢弃，属于草稿箱与领域治理。
- 草稿写入失败记 `failed`，错误摘要写 `draft_submission_failed`，不自动重写、不自动重跑。原始结果随 Worker 进程退出而消失，让研究员重跑一轮比假装还能恢复更诚实。
- 审计事件追加记录消息接收、状态转换、租约取得/释放、Worker 生命周期、运行时事实、处置决定、取消与无敏感信息的错误摘要。
- 同一订阅目标只允许一条有效 Worker Lease。两个入口通过 SQLite 原子条件领取启动权；未领取不得启动第二个 Worker。可领取记录按 `created_at`、`execution_id` 稳定排序。
- 租约失效不覆盖旧记录；恢复必须创建关联旧记录的新记录。续租周期、超时阈值与接管算法不在本规格实现。

### Runtime Adapter 与 Worker

- Gateway 核心依赖 Execution Store、Worker Scheduler 与 Runtime Adapter；首版实现分别为共享 SQLite、本地进程调度与 fast-agent Runtime Adapter。
- Runtime Adapter 至少提供 run、resume 与 cancel。Worker 使用固定 `session_id`、专属持久 home、connection scope 与 session history，默认关闭自动 compaction。
- Worker 正常跑完时把结果写成草稿箱草稿，并把 `draft_id` 交回 Gateway；写入成功才转 `completed`。
- 运行时异常、超时、非零退出或无法恢复会话时转 `failed`。Gateway 重启可读取未完成记录，但不自动重做 `failed` 记录。

### 草稿写入与凭据边界

- 写草稿的不是 Gateway，是 Worker 里的 agent 本身。中央草稿箱的 MCP 作为工具注册给该 Work Agent，agent 在 loop 末尾自行调用 `create_draft`。
- Gateway 不持有草稿箱凭据，也不知道领域命名空间的审核人；它只从 agent 拿回 `draft_id`。
- 草稿箱知道「谁提交了什么」，Gateway 知道「哪一轮执行产出了它」，二者靠 `draft_id` 与 `execution_id` 双向弱引用，不共享存储。

### Centre Agent 的差异

结构与 Task Agent 完全一致，只有三处不同：

| 项 | Task Agent | Centre Agent |
| --- | --- | --- |
| 订阅目标 | 自己负责的 `task_node_id` | 候选创建与候选头更新事件；正式版本发布事件 |
| 一轮 loop 做什么 | 执行科研任务，产出草稿 | 拉全量候选快照做预审，追加报告；必要时新建混合候选 |
| 处置面承接什么 | 返修、放弃、转人工、回答提问 | 列出待审候选、查看报告、要求重算某候选的报告 |

处置面工具名与签名保持一致，但 Centre Agent 当前不提供功能，统一返回 `unimplemented`——中央 Agent 的工作里没有返修。保留同名接口是为了两个实例共用一套骨架。租约在两种实例里都保留，定位是本地单实例互斥，不是跨实例分发。

### 源码放置（2026-10-22）

上文「一个项目组、三个子项目」描述的是**每一份** Work Agent 的进程形状，不是仓库里只有一棵源码树。放置以 [ADR-0002](../../docs/adr/0002-work-agent-two-codebases.md) 为准，本节约定实现必须同时满足的边界：

- 两份源码，禁止互相 path 依赖，也不抽顶层共享包。状态机、Worker Lease、处置面工具改动必须两处一起改。Agent 定义允许不同。
- Centre Agent 的家是 `sci-weave/centre-control/centre-agents`。它是中央服务器上的预审服务，Agent 定义写死，不做成给研究员安装的库。进程仍是两个常驻 gateway 再拉起 `fast-agent-mcp` 子进程。
- 现有 `sci-weave/task-agent/` 只作为迁入 `centre-agents` 的 `git mv` 起点。两处都落地后删除该目录。起点里的 `submit_owner_command` 不是现行契约。
- Task Agent 不在中央运行。发给研究员的是 `sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent`，形态由「建立新 Task Agent 的套件」(ai4-za77) 定义：skill、服务模板、libs。研究员只能改 Agent 定义。
- 研究员机器上的 `gateway/mcp` 与 `gateway/subscriber` 用用户级自启动常驻。hooks 只在打开 harness 时检查，没跑就拉起，不掌管生命周期。

## Testing Decisions

- 以认证后的 MCP 工具调用作为最高且主要的行为测试接缝；测试不检查私有类、表访问顺序、子进程实现细节或日志格式。
- 回环 HTTP 探针只测试最小健康结果，以及它与 MCP `health` 共用健康计算的可观察结果。
- 使用临时 SQLite、临时持久目录、回环地址与系统分配端口 `0`；不得依赖固定部署端口、真实令牌、真实模型凭据或真实队列。
- 在 MCP 处置面验证：认证拒绝、状态查询、待处理排序、取消幂等、回答提问产生 `resume_of`、三种处置决定产生正确状态、`unimplemented` 返回值、稳定错误码。
- 在持久化与调度边界验证：重复 bootstrap、非法状态迁移拒绝、重启后读取、同目标原子租约与串行化、跨目标并发。
- 在 Worker/Runtime Adapter 边界验证：草稿写入成功后转 `completed` 且记录 `draft_id`、草稿写入失败转 `failed`、运行时失败、`waiting` 后产生 `resume_of`、返修后产生 `revision_of`、固定会话恢复、Worker 退出与租约释放。
- 用假队列与假草稿箱驱动订阅器与草稿写入，不让测试依赖 Redpanda 或 TerminusDB 实例。
- 使用 passthrough fast-agent 运行最小集成测试；真实模型提供商不进入测试。
- 项目组级验证至少包含 uv 环境同步、三个子项目可安装、源码编译与 MCP 行为测试。

## Out of Scope

- 消息队列语义本身（主题、分区键、消费者组命名、保留期、`auto.offset.reset`）：由「消息队列协作模型分支」(ai4-te1v) 定义，本规格只依赖「至少一次投递、按目标有序、业务键去重」三条假定。
- 中央草稿箱与两套领域管理 MCP 的实现；本规格只要求它们提供可调用的 MCP 工具。
- Centre Agent 的预审规则、报告格式与门禁：见「中央 Agent 候选预审职能地图」(ai4-fv1r) 下的子票。
- 建立新 Work Agent 的套件形态：见「建立新 Task Agent 的套件」(ai4-za77)。
- 多人身份、TaskNode Owner 授权绑定、OAuth 授权服务器、scope、跨网络或生产级认证部署。
- Agent Kit manifest、Skills/Hooks 模板、多套件定制、ZIP 交付、跨服务器部署。
- A2A 传输、EventBus、真实模型提供商接入、原件二进制传输、生产级自动恢复与租约接管算法。
- 既有 SQLite 数据库 schema migration 方案。

## Acceptance Criteria

- [ ] 三组件项目组、共享 SQLite 持久化边界、单一 Worker 启动权与处置面 MCP v1 契约均已实现
- [ ] 订阅器收到消息即创建 `queued` 记录、领取租约并拉起 Worker；同一目标不并发，跨目标可并发；重复投递不产生第二轮
- [ ] 状态机为 `queued`/`running`/`waiting`/`completed`/`needs_revision`/`rejected`/`human_takeover`/`failed`/`cancelled`，不含 `blocked`、`awaiting_acceptance`、`accepted`，且所有迁移经审计
- [ ] 不存在 `submit_owner_command`；`review_execution` 不接受 `accept`；任务下发只经队列
- [ ] Worker 正常结束时草稿已写入中央草稿箱且记录保存 `draft_id`；写入失败记为 `failed` 并带 `draft_submission_failed`
- [ ] Gateway 不持有草稿箱凭据，草稿写入由 Worker 内的 agent 完成
- [ ] 认证后的 MCP 调用可查询、列出、取消、回答、处置执行；未认证请求不创建任何执行或审计事实
- [ ] Centre Agent 与 Task Agent 共用同一骨架与工具签名，其处置面返回 `unimplemented`
- [ ] 健康状态、未配置组件、降级与不可用状态均可从规定的 MCP 或最小 HTTP 接缝观察
- [ ] 全部测试决策所列行为均有自动化验证，且不依赖真实模型凭据、固定端口或真实队列

> 增补（2026-10-22）：上面的验收仍描述**一份**运行时的行为。放置另见「源码放置」与 [ADR-0002](../../docs/adr/0002-work-agent-two-codebases.md)。实现时 Centre Agent 与研究员套件各有一份源码，行为都要满足上列验收；套件的组成与启动方式在「建立新 Task Agent 的套件」(ai4-za77)。

## Notes

**2026-10-20T07:32:36Z**

2026-10-20：按“整体实现”重新发布为《最小 Task Agent 项目组实现规格》，覆盖 gateway/mcp、gateway/ingest、worker、共享 SQLite、租约、最小 MCP v1、Caller、单一 ExecutionRecord 状态机、健康和测试边界；标记 ready-for-agent。已验证：fer dep cycle 无依赖环；git diff --check 通过。

**2026-10-21T13:08:58Z**

形态变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)：本规格当时描述的是「中央项目组」，而 task-agent 的运行时改由研究员自持。当时只登记了受影响条目，未改正文。

**2026-10-22T09:10:00Z**

2026-10-22 重写。依据 `docs/data-flow/work-agent.md`、[ADR-0001](../../docs/adr/0001-task-dispatch-via-message-queue.md) 与 Project Owner 2026-10-22 的裁决。逐条对照旧正文：

| 旧表述 | 现表述 |
| --- | --- |
| 中央项目组、中央 Gateway 拉起 Worker | 研究员本机的项目组；与 Centre Agent 共用同一架构 |
| `gateway/ingest` 为「未来上游交接预留」的骨架 | `gateway/subscriber` 是常驻消费者，真实订阅中央队列 |
| 三角色项目组的第三角色叫 ingest | 改名 subscriber；`gateway` 是 mcp 与 subscriber 的复合名，不是独立进程 |
| `submit_owner_command` 创建执行 | 删除。任务下发只经消息队列 |
| `review_execution(decision="accept")` | 删除 accept。一审是把草稿转成候选分支，发生在领域管理 MCP |
| 状态机含 `blocked` | 删除。消息到达即证明上游已发布 |
| 状态机含 `awaiting_acceptance`、`accepted` | 删除。正常终点为 `completed` 并保存 `draft_id` |
| 「接纳执行结果不创建领域草稿」 | 反转为：执行结果由 Worker 内的 agent 写成草稿，写成功才算完成 |
| 领域 Buffer 不在本阶段设计 | 草稿箱是执行结果的目的地，作为已注册 MCP 工具被调用；其实现仍不在本票 |
| 「不实现 ingest 消费」「不接真实队列」 | 订阅器真实消费；测试用假队列 |
| 应答 Worker 提问走 `submit_owner_command` 带 `execution_id` | 独立工具 `answer_question` |
| 错误码四个 | 增加 `unimplemented`，用于 Centre Agent 未实现的处置面 |

`deps` 已清空：原依赖 `ai4-yvh2`（执行与接纳状态机融合）早前已关闭，其状态机结论中「接纳」部分被本轮推翻，保留其执行部分。`links` 增加 `ai4-we38` 与 `ai4-za77`。

**2026-10-22T13:16:53Z**

2026-10-22 补入源码放置，不另写规格。两份源码、套件三块、用户级自启动与 hooks 只补启动，见正文「源码放置」与 ADR-0002。行为验收不变，Centre Agent 与研究员套件都要满足。
