---
id: ai4-gvan
status: in_progress
deps: []
links: [ai4-tg3v, ai4-dybh, ai4-jnkn]
created: 2026-10-22T05:20:54Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-tg3v
tags: [audit, centre-control, implementation, enhancement, ready-for-agent]
---
# 留痕包改造为接口层调用账本

把中央留痕共享包从「存储层审计」改造成「接口层调用账本」：只记录对外工具调用（谁、通过什么通道、调了哪个服务与工具、目标、结果、耗时），写操作两阶段、读操作单条，审计库不可写时写操作跑不起来。

## Problem Statement

中央服务器上的各个对外服务（草稿箱、两套领域管理 MCP、注册表等）没有统一的调用记录，审计链回答不了「谁访问了什么、谁做了什么、哪次调用失败了」。

先前交付的共享包按「正式事实变更」设计：写入方必须在自己的 SQLite 事务里调用，字段是 `operation` 枚举与 `previous_state`/`next_state` 一类业务语义。实际只有改写正式事实的少数代码路径能接上，且把「事实变更」与「接口访问」两种语义挤进同一个事件形状。语义收窄为接口层账本后，这个包的形态整体不再成立。

## Solution

一个仅用 Python 标准库实现的共享包，供中央各服务的**对外接口层**调用：登记一次对外工具调用，写入中央统一的审计 SQLite。读调用与写调用都记；写调用先记录后执行，审计库不可写时写调用直接失败。

包的目录已迁到中央部署边界的 `shared/` 下（`sci-weave/centre-control/shared/audit-trail`），包名 `sciweave-audit-trail`、模块名 `audit_trail` 保持不变。本次交付把包内的事件形状、表结构、写入接口、查询接口、测试与 README 全部换成调用账本形态。

## User Stories

1. 作为中央服务运维者，我想让每个对外工具调用都留下一条记录，以便回答「谁在什么时候调用了什么、结果如何」。
2. 作为中央服务运维者，我想让读调用也被记录，以便追溯「谁访问了哪些内容」。
3. 作为审计查询者，我想按调用者过滤调用记录，以便重建某个人在某段时间内的操作链。
4. 作为审计查询者，我想按连接通道过滤，以便把「同一调用者标识经不同通道进来」的调用区分开。
5. 作为审计查询者，我想按被调服务与工具名过滤，以便统计某个工具的使用量与失败率。
6. 作为审计查询者，我想按目标对象标识过滤，以便回答「这个 Proposal / 草稿 / 文档被谁碰过」。
7. 作为审计查询者，我想按结果过滤，以便单独捞取失败的调用。
8. 作为审计查询者，我想按时间区间过滤且结果稳定倒序，以便拼接跨查询的调用链。
9. 作为审计查询者，我想查出「只有 invoked 没有 completed」的调用，以便检出进程崩溃与结果未知的中断。
10. 作为中央服务开发者，我想用一个上下文管理器包住工具函数体就完成两阶段留痕，以便不必在每个工具里手写记录代码。
11. 作为中央服务开发者，我想在不需要上下文管理器的场合直接调用两个底层函数，以便在跨函数流程里手动收尾。
12. 作为中央服务开发者，我想让上下文管理器自动填耗时，以便不必自己计时。
13. 作为中央服务开发者，我想在审计库不可写时让写操作立刻失败，以便不会出现「业务改了但没留痕」。
14. 作为中央服务开发者，我想让读操作在审计库不可写时只告警不中断，以便一次审计故障不会拖垮查询。
15. 作为中央服务开发者，我想用一个函数按环境变量打开审计库连接，以便不必自己拼装 PRAGMA 配置。
16. 作为数据治理责任方，我想让审计库只存参数摘要与对象标识，以便审计库不会变成第二份内容存储。
17. 作为数据治理责任方，我想让审计库拒绝任何入参正文字段，以便这一约束不靠接入方自觉。
18. 作为中央服务开发者，我想让建表函数支持多语句 DDL，以便加索引时不会抛 `ProgrammingError`。
19. 作为中央服务开发者，我想让建表函数幂等，以便重复启动不会失败。
20. 作为审计查询者，我想确认这个包没有任何更新或删除入口，以便账本的不可篡改性不依赖流程约束。
21. 作为中央服务开发者，我想让包在业务事务已开启时明确报错，以便审计记录不会被业务回滚带走。
22. 作为中央服务开发者，我想让 PRAGMA 配置在内存库上静默降级，以便测试不受 WAL 支持差异影响。

## Implementation Decisions

### 归属与范围

改动只发生在 `sci-weave/centre-control/shared/audit-trail` 一个目录内。目录迁移已用 `git mv` 完成，`sci-weave/shared/` 不再保留副本，Git 历史可 `--follow`。

**不触碰其他人负责的内容。** `sci-weave/centre-control/research-map`、`research-wiki`、`buffer`、`centre-agents`、`registery`、`web-ui` 与 `sci-weave/task-agent` 一行都不改；`.tickets/` 下他人 `assignee` 的票不改。`docs/TECH_STACK.md` 的共享代码规则与本目录的 README 说明已在前序提交中同步，本次无需再动。

### 数据形状

表名由 `audit_event` 改为 `audit_call`，语义是「一次调用」而不是「一个事件」。

必填：`call_id`、`occurred_at`、`caller_id`、`channel_id`、`caller_type`、`service`、`tool`、`phase`、`result`。

可选：`target_object_type`、`target_object_id`、`args_digest`、`error_code`、`duration_ms`、`refs`。

`call_id` 与 `occurred_at` 由包生成；`caller_type` 取值限 `human`/`agent`/`system`/`service`，`phase` 限 `invoked`/`completed`/`attempted`，`result` 限 `ok`/`error`/`denied`/`unknown`，三者以 CHECK 约束落在表上。`checks` 一类的业务语义字段一律不建。

`args_digest` 是调用方算好的入参摘要字符串，包只存不算；`refs` 是 JSON 文本兜底字段，读写往返无损。表结构不含任何自由文本入参列——这一约束由「表里没有那一列」保证，不靠文档约定。

索引三条：`(service, tool, occurred_at)`、`(target_object_id, occurred_at)`、`(caller_id, occurred_at)`。

### 写入语义

**读调用 fail-open。** 单条 `phase='attempted'` 记录，`result` 固定 `unknown`（读调用结束时调用方仍可用 `finish_call` 补一条 `completed`，本包不强求）。写入失败记一条 `WARNING` 级日志后返回 `None`，调用方照常返回业务结果。

**写调用两阶段。** `begin_call` 落 `phase='invoked'`，失败抛异常且**业务一行都不执行**；业务结束调用 `finish_call` 落第二条 `phase='completed'`，两条共用同一个 `call_id`。业务失败同样要调 `finish_call`，`result` 记 `error` 并带 `error_code`。

**`finish_call` 失败不回滚业务。** 它记一条 `WARNING` 后返回，库里留下一条未配对的 `invoked` 作为缺口证据。这与父票的表述一致：父票明说「业务已提交但 completed 写失败时，缺口表现为一条未配对的 invoked」，因此第二阶段的失败不能反过来要求回滚已提交的业务。两阶段的保证是**审计库不可用时写操作跑不起来**，不是跨库原子。

**审计库不与业务事务共用连接。** 每次追加前检查连接的 `in_transaction`：为真则抛异常，说明账本追加不能加入业务事务（否则业务回滚会连带删除审计记录，与 fail-closed 的前提相反）。为假时包自己用 `BEGIN IMMEDIATE` 开事务、追加、立即提交，不跨业务操作。

**耗时用单调时钟。** `duration_ms` 由 `time.monotonic()` 前后差计算，不用墙钟；`occurred_at` 仍用 UTC 墙钟。这样系统对时跳变不会产生负数或异常大的耗时。

### 接口

`CallRecord`（dataclass）：调用记录形状与字段校验，不含 `call_id`、`occurred_at`、`phase`、`result`。

`open_connection(path=None)`：按 `SCIWEAVE_AUDIT_SQLITE_PATH` 打开连接并设 PRAGMA，返回 `row_factory` 已设好的连接。本函数不读 `.env`、不建表——`.env` 由 `uv run --env-file` 注入。

`init_audit_table(conn)`：建表并设 PRAGMA，幂等。必须用 `executescript` 执行多语句 DDL——旧实现用单条 `execute`，加索引即抛 `ProgrammingError`。

`record_attempted(conn, record)`：读调用的单条记录，fail-open。

`begin_call(conn, record)` / `finish_call(conn, call_id, *, result, error_code=None, duration_ms=None)`：写调用的两阶段。

`call_scope(conn, record, *, error_code=None)`：上下文管理器，内部调上述两阶段并自动填 `duration_ms`；正常退出记 `ok`，抛异常记 `error` 后原样重抛。这是推荐的用法，接入方的装饰器只需包住这个上下文管理器。

`query_audit_calls(conn, *, caller_id=None, channel_id=None, service=None, tool=None, target_object_id=None, result=None, occurred_after=None, occurred_before=None)`：只读查询，时间倒序（`occurred_at DESC, rowid DESC`）。

`find_unfinished_calls(conn, *, occurred_after=None)`：返回只有 `invoked` 没有配对 `completed` 的调用。

**旧接口全部删除，不留别名**：`write_audit_event`、`AuditEvent`、`TransactionRequiredError`、`Operation`、`ActorType` 一并移除。全仓库零引用，留兼容层反而会让后来者误以为同事务写法仍合法。异常类型改为 `AuditValidationError`（字段非法）与 `AuditUnavailableError`（审计库不可写）。

**装饰器与 MCP 中间件不在包内。** 包只提供可被它们调用的函数与上下文管理器；接入方在 MCP 层实现装饰器，工具函数把 `target_object_type` / `target_object_id` / `args_digest` 作为上下文传入。

### 配置

| 变量 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `SCIWEAVE_AUDIT_SQLITE_PATH` | 是 | 无 | 审计库文件路径 |
| `SCIWEAVE_AUDIT_BUSY_TIMEOUT_MS` | 否 | `5000` | SQLite `busy_timeout` |
| `SCIWEAVE_AUDIT_JOURNAL_MODE` | 否 | `WAL` | `journal_mode` |

数值与模式有默认值不违反「路径与地址不得硬编码」——那条约束管的是部署路径、监听地址与端口。本包不提交 `.env.example`：它不是一个可独立启动的部署单元，三个变量由各接入方写进自己的 `.env.example`。

内存库不支持 WAL，PRAGMA 设置失败时静默跳过（记 `DEBUG` 日志），不能让测试因此失败。

### 版本

`pyproject.toml` 的版本从 `0.1.0` 提到 `0.2.0`。这是不兼容的形状变更，但零引用意味着不需要迁移；提次版本号是为了让日后排查的人一眼看出形状换过。

### 日志

标准库 `logging`，logger 名 `audit_trail`，只发 `WARNING`（fail-open 吞异常、`finish_call` 失败）与 `DEBUG`（PRAGMA 降级）。不写文件、不发事件、不重试——本包不管日志落盘，接入方自己配 handler。

## Testing Decisions

**唯一 seam 是包的公共 API。** 不为测试新增内部接缝：所有用例通过 `audit_trail` 导出的函数与 `CallRecord` 驱动，断言数据库里的行与查询返回值。这与既有测试的组织方式一致。

测试用两种连接：内存库跑快速用例；临时文件库跑需要真实验证 WAL 与多进程可写性的用例（用 `tempfile` 生成路径，不复用固定部署路径）。

覆盖：

- 建表幂等：连续两次 `init_audit_table` 不报错，索引存在
- 多语句 DDL：建表后索引可用（旧实现会在这里抛 `ProgrammingError`）
- 单条读调用记录：`record_attempted` 后能查回一行，`phase='attempted'`
- 读调用 fail-open：用只读文件或关闭的连接构造写入失败，断言返回 `None` 且不抛异常
- 两阶段配对：`begin_call` 后 `find_unfinished_calls` 能查到；`finish_call` 后不再出现；两条记录共用 `call_id`
- 写调用 fail-closed：审计库不可写时 `begin_call` 抛 `AuditUnavailableError`
- `finish_call` 失败不抛：构造第二阶段失败，断言只返回、库里留下未配对 `invoked`
- `call_scope` 正常路径记 `ok`、异常路径记 `error` 后原样重抛，且 `duration_ms` 非空
- 业务事务保护：连接已 `BEGIN` 时追加抛异常
- 事务自管：连接干净时追加后 `conn.in_transaction` 为假（已提交）
- 六个过滤维度加时间区间各自生效，结果时间倒序稳定
- `args_digest` 与 `refs` JSON 往返无损
- 表结构不含自由文本入参列：直接读 `PRAGMA table_info`，断言列名集合与预期完全一致（多一列就失败）
- 无 update / delete：导出的名字里没有对应函数，且 `audit_call` 表无 `UPDATE`/`DELETE` 语句（读源码断言或直接断言 API 集合）
- 内存库 PRAGMA 降级：对 `:memory:` 建表不抛异常

## Out of Scope

- **不接任何真实服务。** 草稿箱、Mapping 管理 MCP、Wiki 管理 MCP、注册表都还没有 MCP 层；接入由各自实现票在 MCP 层落地时完成。
- **不实现装饰器或中间件。** 包只提供被它们调用的函数与上下文管理器。
- **不改端侧执行遥测。** `sci-weave/task-agent` 的 `audit_events` 保持现状，端侧不写中央账本。
- **不改领域治理记录。** Mapping / Wiki / Buffer 各自的审计表与正式事实记录不接本包、不迁移、不合并。
- **不做身份校验。** `caller_id` 由调用方套件提供，包与 MCP 入口都不解析、不校验；多人共用一个套件时账本会合并为同一标识，这是已接受的限制。
- **不加幂等键。** 同一调用重复记录就是两条记录；去重不在本包。
- **不建独立审计服务、不建 MCP 工具、看板不在此**。查询是进程内函数。
- **不做历史数据迁移。** `audit_event` 表从未在任何环境建过，无存量数据需要转换。

## Further Notes

**对「本地日志」的回答。** 你问的「还需要本地日志吗」：包本身只往标准库 logger 写 `WARNING`/`DEBUG`，不落文件。理由是审计记录已经落在 SQLite 里，再写一份文本日志会形成第二份不可信副本；而 fail-open 场景必须留下一点痕迹，logger 是最轻的形式，落不落盘由接入方的 handler 配置决定。

**`occurred_at` 精度统一到微秒。** 旧实现在此没有分歧，保持 `timespec="microseconds"`，避免与其他时间字段混用不同精度排序不稳。

**现状核对（2026-10-22）。** 目录迁移已完成且 Git 识别为 rename；迁移后旧测试 11 个项目全绿，说明迁移本身未破坏任何东西。包内源码仍是旧的存储层审计形态：`audit_event` 表、`Operation` 五枚举、`conn.in_transaction` 校验、`conn.execute(_SCHEMA_SQL)` 单语句 DDL。全仓库对本包零引用，无下游需要跟随。
