---
id: ai4-tg3v
status: open
deps: []
links: [ai4-dybh, ai4-gvan]
created: 2026-10-22T01:20:55Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-fv1r
tags: [spec, centre-control, audit, ready-for-agent]
---
# 中央留痕工具共享包实现规格

中央服务器的对外服务（草稿箱、Research Mapping 管理 MCP、LLM-Wiki 管理 MCP、注册表等）在**接口层**统一记录「谁通过什么通道调用了哪个工具、目标是什么、结果如何」。留痕只发生在对外接口，模块内部不调用。

## Problem Statement

中央服务器上的多个组件各自实现对外接口，但没有统一的调用记录：审计链无法回答「谁访问了什么、谁做了什么、哪次调用失败了」。既有尝试把留痕做成存储层能力（写入方在自己的 SQLite 事务里调用），实际只有改写正式事实的少数代码路径能接上，且把「正式事实变更」与「接口访问」两种语义混在一个事件形状里。

## Solution

提供一个仅用 Python 标准库实现的共享包 `audit_trail`，供中央各服务的**对外接口层**调用：登记一对外调用（谁、哪个通道、哪个服务、哪个工具、目标、结果、耗时），写入中央统一的审计 SQLite；读操作与写操作都记；写操作先记录后执行。

## Destination 与边界

**只记接口层的对外调用。** 语义留在业务侧：调用的业务含义（改了哪个字段、批了哪个提案）由消息内容、Mapping 或 Wiki 自己的治理记录承担，审计账本不重复表达。

**模块内部不调用。** 领域服务内部的函数调用、事务、内部状态迁移不产生审计记录。

**端侧不接。** `sci-weave/task-agent` 的执行遥测留在它自己的 `audit_events` 表，由 Gateway 与 fast-agent-mcp 自身日志承担；端侧不写中央审计账本。

## User Stories

1. As a 中央服务运维者, I want 每个对外工具调用都留下一条记录, so that 能回答「谁在什么时候调用了什么、结果如何」。
2. As a 中央服务运维者, I want 读调用也记录, so that 「谁访问了哪些内容」可追溯。
3. As a Project Owner, I want 按调用者、服务、工具、目标对象、结果和时间过滤, so that 能重建某次访问或某段窗口内的调用链。
4. As a 中央服务开发者, I want 用装饰器或上下文管理器包住工具函数就完成留痕, so that 不需要在每个工具里手写记录代码，也不会漏记。
5. As a 中央服务开发者, I want 写操作在执行业务前先记录 invoked、成功后记录 completed, so that 审计库不可用时写操作直接失败而不是静默通过。
6. As a 审计查询者, I want 能找出只有 invoked 没有 completed 的调用, so that 崩溃与中断可被检出。
7. As a 数据治理责任方, I want 审计库只存参数摘要不存入参正文, so that 审计库不会变成第二份内容存储。
8. As a 中央服务开发者, I want 各部署单元用环境变量决定审计库路径并在启动时传给共享包, so that 各进程可指向同一库或各自的库，而共享包本身不读取环境。
9. As a 端侧 Agent 维护者, I want 端侧不接入这个包, so that 端侧不新增中央耦合。

## Implementation Decisions

### 位置

`sci-weave/centre-control/shared/audit-trail`，包名 `sciweave-audit-trail`，模块名 `audit_trail`，`requires-python >= 3.11`，仅标准库。调用方以 uv `[tool.uv.sources]` path 可编辑依赖引用。

`centre-control` 不是项目组、各目录不共用锁文件；`shared/` 在这里是**代码归属边界**，表示「部署在中央的多个独立项目共用这段代码」。`docs/TECH_STACK.md` 的共享代码规则已按此写明。

### 存储

中央约定只有一个审计 SQLite。路径不由共享包读取：各部署单元在自己的 `.env.example` 声明 `SCIWEAVE_AUDIT_SQLITE_PATH`，进程启动时读出并传给 `open_connection`。两个进程传入不同路径就会拆成两个账本，跨服务查询不再成立；同库是部署约定，不是包内强制。多个服务的进程写同一个库文件时使用 `journal_mode=WAL`（默认），`busy_timeout` 默认 5000 毫秒，两者都是 `open_connection` 的参数，不是环境变量。写入以 `BEGIN IMMEDIATE` 加锁后立即提交，单条追加不跨业务事务。

存储不按服务分库：跨服务视图是选「一个库」的核心理由。领域治理记录（Mapping / Wiki / Buffer 各自的事实与状态）仍留在各自存储，不搬进审计库。

**连接由调用方复用。** 进程启动时打开一次，并调用一次 `init_audit_table`，之后整段生命周期复用这条连接，退出时由调用方关闭。打开或建表失败时包抛 `AuditUnavailableError`，不自己退出进程；调用方在开始对外服务之前必须完成这两步，任一步失败则不起服务。运行中的单次失败不改：写调用失败则业务不执行，读调用失败只告警。包不代管开关，也不加锁。同一时间只有一个线程使用这条连接；并发请求由调用方在包外串行化。

### 事件形状（调用账本）

必填：

| 字段 | 含义 |
| --- | --- |
| `call_id` | 一条调用链的标识；两阶段写入时两条共用 |
| `occurred_at` | 由包生成，UTC ISO8601 |
| `caller_id` | 套件调用标识，由调用方套件填入，**不是** Gateway 的 Caller。MCP 入口不解析、不校验 |
| `channel_id` | 连接通道标识，取自服务启动配置，用于与 `caller_id` 对照 |
| `caller_type` | `human` / `agent` / `system` / `service` |
| `service` | 被调用的中央服务名，如 `mapping-mcp` |
| `tool` | 工具名 |
| `phase` | `invoked` / `completed` / `attempted`（读操作单条用 `attempted`） |
| `result` | `ok` / `error` / `denied` / `unknown` |

可选：`error_code`、`duration_ms`、`args_digest`、`target_object_type`、`target_object_id`、`refs`（JSON 兜底）。

**不留正文。** `args_digest` 是调用方算好的不透明摘要字符串，包只存不算，不规定算法。`target_object_id` 只放对象标识，任何入参正文、草稿内容、Wiki 正文都不落审计库。

### 写入时机

- **读工具**：调用结束后追加一条 `phase=attempted`，`result` 固定 `unknown`。到此为止，不能再用 `finish_call` 补 `completed`。写审计失败只记本地告警，调用照常返回（fail-open）。
- **写工具**：调用前追加 `phase=invoked`；**这次写入失败则不执行业务操作**（fail-closed），向调用方返回错误；业务成功后追加 `phase=completed`。业务失败也追加 `completed` 记 `result=error`。进程在两次写入之间崩溃时，库里留下一条没有配对的 `invoked`，即「中断或结果未知」。
- 两阶段不保证跨库原子（审计库与领域存储是不同数据库），它保证的是**审计库不可用时写操作跑不起来**；业务已提交但 `completed` 写失败时，缺口表现为一条未配对的 `invoked`。

### 接口

- `CallRecord`：事件 dataclass 与字段校验。
- `init_audit_table(conn)`：建表；DDL 必须支持多语句（现有实现用单条 `conn.execute` 跑多语句会抛 `ProgrammingError`）。
- `record_attempted(conn, record)`：读工具单条记录。成功返回 `call_id`，失败返回 `None` 且不抛。
- `begin_call(conn, record) -> call_id` / `finish_call(conn, call_id, *, result, error_code, duration_ms)`：写工具两阶段。`finish_call` 只配对还没有 `completed` 的 `invoked`。对不上（没有这条 `invoked`、已经配过、或只有 `attempted`）抛 `AuditValidationError`，不另插一行。数据库写失败只告警、不抛，留下未配对的 `invoked`。
- `call_scope(...)`：上下文管理器，封装两阶段，供装饰器使用。
- `open_connection(path, *, busy_timeout_ms=5000, journal_mode="WAL")`：按调用方传入的路径打开连接并设 PRAGMA。`path` 必填。本函数不读环境变量、不读 `.env`、不建表。保持 SQLite 默认的 `check_same_thread=True`，包内不加锁。
- `query_audit_calls(conn, *, caller_id=None, channel_id=None, service=None, tool=None, target_object_id=None, result=None, occurred_after=None, occurred_before=None)`：只读，时间倒序（`occurred_at DESC, rowid DESC`）。
- `find_unfinished_calls(conn, *, occurred_after=None)`：返回只有 `invoked` 没有 `completed` 的调用。

装饰器与 MCP 中间件**不在本包内**：包只提供可被它们调用的函数。装饰器由接入方在 MCP 层实现，工具函数把 `target_object_type` / `target_object_id` / `args_digest` 作为上下文传入。

### 不做什么

- 不提供更新或删除接口；只追加。
- 不加幂等键。两次独立调用就是两条记录；这和 `finish_call` 拒绝重复配对不是一回事。
- 不做身份校验、不查注册表、不解析令牌。
- 不定义业务语义字段（`operation` 枚举、`previous_state`、`next_state`、`base_revision`、`formal_revision_id` 等全部删除）。
- 不建独立审计服务、不建 MCP 工具、不暴露给 Agent 自由写入。

## Testing Decisions

唯一 seam 是包的公共 API。测试用临时 SQLite 文件（验证 WAL 与真实文件行为）与内存库（快速用例）。

覆盖：

- 单条追加与查询回读，时间倒序稳定
- 两阶段：`begin` + `finish` 配对可查；只有 `begin` 的调用出现在 `find_unfinished_calls`；被 `finish` 后不再出现
- `finish_call` 对不上未配对的 `invoked` 时抛 `AuditValidationError`，不插入；读调用的 `attempted` 不能被配成 `completed`
- fail-closed：审计库不可写时 `begin_call` 抛错（用只读文件或关闭的连接构造）
- 按 `caller_id` / `channel_id` / `service` / `tool` / `target_object_id` / `result` / 时间区间过滤
- `args_digest` 与 `refs` JSON 往返无损；确认表结构没有任何自由文本入参字段
- 无 update / delete 公共 API
- 多语句 DDL 可执行（加索引后仍能建表）

## Out of Scope

- 真实接入任何中央服务：MCP 层尚不存在，接入由各服务实现票完成。
- 端侧审计：`sci-weave/task-agent` 不在调用方集合内。
- 领域治理记录：Mapping / Wiki / Buffer 的审计表属于领域自身，不接本包、不迁移、不合并。
- 中央身份体系：`caller_id` 由套件提供，本包与 MCP 入口都不校验；多人共用套件时账本会合并为一条，这是已接受的限制。
- 独立查询服务与看板：查询是进程内函数，看板后续自行包装。

## Acceptance Criteria

- [ ] 位置、包名、模块名与依赖形态按本票确定，`centre-control/README.md` 与 `docs/TECH_STACK.md` 同步
- [ ] 事件形状为调用账本，不含任何业务语义字段
- [ ] 读工具 fail-open 单条记录；写工具 fail-closed 两阶段记录，且能用测试证明审计不可用时写操作被阻断
- [ ] `find_unfinished_calls` 能检出未配对调用
- [ ] 共享包不读取环境变量、不提交 `.env.example`；`open_connection` 的路径必填。各接入方在自己的 `.env.example` 声明 `SCIWEAVE_AUDIT_SQLITE_PATH` 并在启动时传入。打开或建表失败时调用方不起服务
- [ ] 审计库不含入参正文，只含摘要与对象标识
- [ ] 无 update / delete API；多语句 DDL 可用
- [ ] 回归测试全绿，README 示例可直接运行

## Notes

**2026-10-22T00:00:00Z**

本票经 wayfinder grilling 收口。设计树见与 Frank Qi 的逐轮问答（2026-10-22 三轮）。

决策记录：

1. **语义边界**：统一留痕只记接口层对外调用，读写都记；业务语义留在消息、Mapping、Wiki 自己的记录里。
2. **位置**：搬到 `sci-weave/centre-control/shared/audit-trail`；中心组件一起迁移，`shared/` 是中央代码归属边界。
3. **端侧退出**：task-agent 保持现有 `audit_events`，执行过程追溯靠 fast-agent-mcp 自身日志与 ExecutionRecord 状态机。
4. **存储**：中央一个审计库，路径可配置；跨服务视图依赖同库。
5. **调用者身份**：`actor_id` 由调用方套件提供，MCP 入口不规定、不解析；另记 `channel_id` 供对照，不做一致性校验。
6. **写入时机**：写操作先记录后执行（fail-closed），读操作后记录且 fail-open。
7. **事件形状**：调用账本字段，删除全部业务语义字段；只留参数摘要，不留正文。
8. **留痕位置**：装饰器包住工具函数，拿不到的业务语义不反推，只记工具名与对象标识。

**2026-10-22T13:20:00Z**

本票正文已按上述决策整体改写。原文（存储层审计、`write_audit_event(conn, event)` 同事务约束、5 个 operation 枚举、Mapping/Wiki/Buffer 各自落库）作废，作废依据记录在「中央服务留痕工具：写入方统一调用的审计接口」(ai4-upsm) 的修订说明中。

代码落地由 [留痕包迁移到 centre-control 并改造为接口层调用账本](ai4-gvan.md) 承担。

**2026-10-23T00:00:00Z**

现行表述与实现票对齐，旧名字只留在上面的决策记录里：

1. 字段名用 `caller_id`，不用决策记录第 5 条里的 `actor_id`。查询函数用 `query_audit_calls`，不用 `query_audit_events`。
2. 共享包不读环境变量，也不提交 `.env.example`。`open_connection(path, *, busy_timeout_ms=5000, journal_mode="WAL")` 的路径必填；`SCIWEAVE_AUDIT_BUSY_TIMEOUT_MS` 与 `SCIWEAVE_AUDIT_JOURNAL_MODE` 不再作为环境变量。各接入方在自己的 `.env.example` 声明 `SCIWEAVE_AUDIT_SQLITE_PATH`，启动时传入。同库仍是部署约定。
3. 连接在进程启动时打开一次并复用，`init_audit_table` 也在启动时调一次。包保持 `check_same_thread=True`，不加锁；并发由调用方在包外串行化。
4. `caller_id` 的术语是套件调用标识，不是术语表里的 Caller。
5. 打开或建表失败时包抛 `AuditUnavailableError`，不自己退出进程。调用方在开始对外服务之前完成这两步，任一步失败则不起服务。运行中的单次失败仍按原规则。
6. 读调用只有一条 `attempted`，不能用 `finish_call` 补 `completed`。`finish_call` 只配对尚未完成的 `invoked`；对不上抛 `AuditValidationError`，不另插一行。数据库写失败仍只告警、不抛。不加幂等键：两次独立调用仍是两条记录。
