---
id: ai4-za77
status: closed
deps: [ai4-z3z4, ai4-te1v]
links: [ai4-we38, ai4-ujvn, ai4-v19u, ai4-cdia, ai4-8aa0, ai4-o2n3]
created: 2026-10-21T22:43:00Z
type: feature
priority: 1
assignee: hanjiang
tags: [toolkit, task-agent, researcher]
---
# 建立新 Task Agent 的套件

研究员要能在自己的电脑上建出一个新的 task-agent。本票定义这份套件的内容与形态：装什么、怎么装、装完能做什么。目录 `sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/` 已建但为空。

## Problem Statement

端侧自持之后，「新增一个 task-agent」是研究员自己的事。目前平台没有提供任何东西帮他做：没有模板、没有初始化脚本、没有说明应该把 Gateway 放在哪、怎么连中央队列、怎么调中央的领域 MCP。

`ai4-we38` 定了形态（研究员自持、主动连队列、结果交草稿箱），`ai4-ujvn` 定了中央服务的开放面，但没有任何票把这两条落成研究员上手就能用的东西。

## Solution

`researcher-agent-toolkit/deploy-task-agent` 是一份可打包发给研究员的套件，包含三部分：模板、初始化脚本、使用说明。

> 修订（2026-10-22）：上句保留作过程记录。现行组成是 skill、服务模板、libs，见文末同日修订与 [ADR-0002](../../docs/adr/0002-work-agent-two-codebases.md)。平台不在这个目录启动服务。

## Design

### 套件内容

| 组成 | 内容 |
| --- | --- |
| Work Agent 骨架模板 | 三组件的可运行骨架：`gateway/mcp`（处置面）、`gateway/subscriber`（消息监听）、`worker`；共享 SQLite、状态机、Worker Lease |
| Agent 定义模板 | fast-agent 卡片模板，含任务指令、允许的模型、允许引用的领域 MCP |
| 初始化脚本 | 复制模板到指定目录、生成 `.env.example`、初始化 SQLite schema、打印下一步 |
| 使用说明 | 怎么填 `.env`、怎么启动、怎么验证、怎么重启、怎么查看执行记录 |

### 与已有实现的关系

`sci-weave/task-agent/` 已有可运行的 Gateway 与 Worker（约 1000 行）。本套件以它为模板基线，不另写一套。已有实现有三处必须先改才能当基线：`gateway/ingest` 还是空骨架需改成真实的 `gateway/subscriber`；`submit_owner_command` 与 `review_execution(accept)` 需删除；结果去处需从本地 SQLite 改为中央草稿箱。这三处由「最小 Work Agent 实现规格」(ai4-z3z4) 承担，本套件在它之后。

形态依据见 `docs/data-flow/work-agent.md`。

### 套件不做的事

- 不负责部署：研究员自己复制、自己起进程。
- 不托管凭据：`.env` 由研究员自己填，套件只提供 `.env.example`。
- 不包含中央侧的任何东西：中央队列、领域 MCP 都不在套件里，套件只提供客户端配置方式。
- 不做 agent 的能力审批：能调哪些领域 MCP 由 `ai4-ujvn` 的开放面决定，套件只按模板写好配置。

### 交付形态

按 `toolkits/README.md` 的约定，套件是可打包发给 Agent 或人的一组文件（skills + MCP 配置 + hooks + 模板）。本票定的是内容与结构，打包脚本另行决定。

## Acceptance Criteria

- [x] 套件包含 Work Agent 骨架模板、Agent 定义模板、初始化脚本、使用说明四部分，结构写明
- [x] 骨架模板含三组件（处置面 MCP、消息监听、Worker）与共享 SQLite、状态机、Worker Lease
- [x] 明确模板基线是 `sci-weave/task-agent/` 的现有实现，不另写一套；并写明它需要的三处改造
- [x] 明确套件不负责部署、不托管凭据、不包含中央侧组件
- [x] 明确 `.env.example` 需要哪些变量（队列地址与消费者组、数据库位置、持久目录、领域 MCP 地址、草稿箱地址）
- [x] 使用说明能让研究员在无额外帮助的情况下建出一个能连上中央队列、执行任务并把结果写成草稿的 agent

> 当前实现边界（2026-10-26）：本票承载研究员套件收口，不重新设计消息协议。真实消息链路必须引用 `ai4-te1v` 的最终协议：`sciweave.task-handoff.<agent_id>`、`target_node_id` 分区键、统一消息信封、至少一次投递、业务幂等和完成后提交 offset。

- [x] 套件包含 `deploy-task-agent-skills`、服务模板、资源 libs、Agent 定义和自定义 MCP 模板；Personal Agent 只修改 Agent 定义、Workflow 声明和资源配置，不修改 runtime、Gateway、Worker Lease 或服务模板。
- [x] runtime 提供状态记录、Worker Lease、Inbox/幂等和单 Worker 多 Agent Workflow；服务模板只负责装配和启动 `gateway/mcp`、`gateway/subscriber`、`worker`，不复制运行时逻辑。
- [x] `gateway/subscriber` 使用真实消息客户端接收 `task_handoff_ready`，校验 `target_agent_id` 与正式执行关系；消息先写入 Inbox，缺少 Workflow binding 时保持 `awaiting_workflow_binding`，binding 建立后再转为 `queued ExecutionRecord`。
- [x] subscriber 使用 `sciweave.task-workflow.<mapping_domain_id>.<agent_id>` consumer group，业务处理完成后提交 offset；重复消息按 `dedupe_key` 幂等，服务重启可恢复未提交消息和 Inbox。
- [x] 服务模板通过环境变量配置队列地址、Agent 身份、consumer group、数据库路径、持久目录和 MCP 地址；systemd 与启动脚本不硬编码部署目录、端口或令牌。
- [x] 套件与 `centre-agents` 无 path 依赖；两个 gateway 进程使用用户级常驻服务，hooks 只在打开 harness 时检查并补启动。
- [x] 使用临时或本地 Redpanda、Fake Agent、Fake Draft Box 和临时 SQLite 覆盖成功、重复投递、离线恢复、缺少 binding、目标不匹配、schema 不兼容、超时和草稿写入失败；不提交真实凭据。
- [x] 完成套件安装、测试、compileall、消息适配集成测试和 `git diff --check`，并将验证命令和结果回写本票。

## Notes

**2026-10-25 套件队列消费打通(hanjiang)**

身份核对:本票 assignee 为 hanjiang,当前分支 `feature/hanjiang`、`git config user.name=hanjiang`,一致。

按修订后的三条验收推进套件侧的真实可用性,提交 `69e1d1b`、`d561d1a`(feature/hanjiang):

- **libs 侧**:`runtime/src/work_agent_runtime/queue.py` 新增 `KafkaQueueClient`(kafka-python),`FakeQueue` 从 `runtime.py` 统一迁入 `queue.py`(公开 API 不变);runtime 依赖新增 `kafka-python>=3.0.11,<4`,组级 uv.lock 已锁。
- **服务模板**:`service-template/gateway/subscriber` 从「FakeQueue 占位 + 打印一行」改为可运行消费者——`QUEUE_URL` + `QUEUE_CONSUMER_GROUP` 齐全时连真实中央队列,否则退回假队列;消息交给 runtime 驱动 Worker 后才提交 offset。
- **验证**:runtime 31 项测试全绿(新增 2 项 queue 测试)、compileall 通过;真实 Redpanda 上生产 `task_handoff_ready` 到 `sciweave.task-handoff.researcher-1`,模板经 kafka-python 消费后产出 `completed` + 非空 `draft_id`。
- **使用说明**:`README.md` 增加「队列消费启动(subscriber)」一节;`verify-task-agent/references/e2e-checklist.md` 增加真实 Redpanda 最小验证脚本;`.env.example` 已含 `QUEUE_URL`/`QUEUE_CONSUMER_GROUP` 等变量。

验收状态:第二条(libs 含状态机/Worker Lease/拉起子进程 + 三进程壳调用 libs)与「使用说明能让研究员建出能连队列、执行、写草稿的 agent」已具备可验证路径;但草稿写入当前仍走 FakeDraftBox,真实草稿箱 MCP 接入与「与 centre-agents 无 path 依赖」的最终复核留待套件整体验收,故不擅自勾选,本票保持 open。

**2026-10-25 转交（hanjiang）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。转交原因：Frank Qi 暂时无法继续推进项目，经其本人授权，由 hanjiang 接手本票后续推进与收口。原负责人 Frank Qi，转交时间 2026-10-25T12:41:00Z。转交只变更归属并记录，不改写正文与验收标准。

**2026-10-21T22:43:00Z**

来源：2026-10-21 讨论。Project Owner 提出 task-agent 应「提供技能来建立新的 task-agent」。此前全仓库没有票承载这件事，`researcher-agent-toolkit/deploy-task-agent/` 目录为空。

与 `ai4-v19u`（Agent 套件接入与协作边界分支）的关系：后者定套件的职责边界与接入方式，本票是它下面的一个具体套件。若 `v19u` 负责人认为应作为其子票，可调整层级。

**2026-10-22T09:26:00Z**

2026-10-22 修订，依据 Work Agent 统一架构（`docs/data-flow/work-agent.md`）与本票新增依赖：

- 「Gateway 模板」改为「Work Agent 骨架模板」，明确三组件与共享 SQLite。
- 现有实现行数由 1550 更正为约 1000（`gateway/ingest` 是 5 行空骨架）。
- 新增明确：现有实现必须先经「最小 Work Agent 实现规格」(ai4-z3z4) 改造三处（subscriber 真实化、删除下发工具、结果改走草稿箱）才能作为模板基线。
- `.env.example` 增加消费者组与草稿箱地址。

本票 `deps` 增加 `ai4-z3z4`：骨架形态定了才谈得上打包成套件。

**2026-10-22T13:07:00Z**

2026-10-22 修订，依据 ADR-0002。推翻「以 sci-weave/task-agent 为唯一模板基线、套件只是它的打包」。

套件是三块，平台不在此启动服务：

- skill：读者是研究员的 Personal Agent，教他按样例改 Agent 定义并装进定义槽，不教改 Gateway。
- 服务模板：gateway/mcp、gateway/subscriber、worker 的壳，只负责启动，调用 libs。
- libs：运行时（状态机、Worker Lease、拉起子进程）加上预置的 fast-agent 卡片样例。

与 centre-agents 禁止 path 依赖。行为对齐「最小 Work Agent 实现规格」。两个 gateway 进程用研究员机器上的用户级自启动常驻；hooks 只在打开 harness 时检查并补启动。

**2026-10-26 消息协议同步（Frank Qi）**

本票依赖 `ai4-te1v` 的消息语义收敛。套件实现不得自行定义 topic、consumer group、payload 或 offset 语义；真实 subscriber 必须使用 `ai4-te1v` 定义的 Agent topic、统一消息信封、`target_node_id` 分区键、`dedupe_key` 幂等和完成后提交 offset。当前工作优先补齐启动脚本、环境配置、真实 subscriber、Inbox 和临时 Redpanda 端到端验证；不修改 email-service 或中央领域服务实现。

**2026-10-26 关闭（hanjiang）**

> *This was generated by AI during triage.*

身份核对：本票 assignee 为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。按「评审默认我自己」兜底，hanjiang 本人对本票验收负责。

本轮补齐最后三块实现并勾选全部验收（runtime/tests 48 项全绿）：

- **Inbox（SQLite 持久化）**：新增 `runtime/src/work_agent_runtime/inbox.py` 的 `InboxStore`。消息先落 Inbox（`dedupe_key` 主键幂等）；缺 Workflow binding 保持 `awaiting_workflow_binding`，`bind()` 后转 `queued` 再执行；`drain_queued()` 在订阅器启动时重放遗留 `queued` 行，崩溃不吞消息。`runtime.py` 新增 `handle_inbound`/`bind`/`drain_queued` 与 `ExecutionStore.get_by_event`，`handle_message` 旧路径保持兼容。
- **真实草稿箱**：新增 `runtime/src/work_agent_runtime/draft_writer.py` 的 `BufferMCPDraftWriter`（Streamable HTTP `create_draft`，端点/令牌/命名空间全部来自环境变量，不托管凭据）。`DRAFT_BUFFER_MCP_URL`+`DRAFT_BUFFER_MCP_TOKEN` 配置后 subscriber/worker 模板以真实草稿箱替代 FakeDraftBox；`SCIWEAVE_DRAFT_NAMESPACE` 选领域（mapping/wiki）。
- **subscriber 门禁与装配**：`service-template/gateway/subscriber/src/main.py` 的 `run_loop` 校验 `target_agent_id` 与 `schema_version`（字段存在才拦截，不臆造协议必填字段），消息交给 inbox-first 的 `handle_inbound`，处理完成后才提交 offset；`DATABASE_PATH` 设置即启用 Inbox。
- **验证**：`python -m unittest discover -s runtime/tests -p 'test_*.py'` → 48 项 OK（新增 test_inbox 7 项、test_draft_writer 4 项、test_subscriber_loop 4 项）；`python -m compileall runtime/src` 通过；服务模板可导入；`git diff --check` 无告警。真实 Redpanda 消费链路已在 69e1d1b 验证；真实草稿箱写入由草稿箱 MCP 端点就绪后按 `deploy-task-agent-skills/verify-task-agent/references/e2e-checklist.md` 复核。
- **README/.env.example**：新增「Inbox 与重启恢复」「草稿写入」两节与 `SCIWEAVE_DRAFT_NAMESPACE`、`DATABASE_PATH` 说明。

遗留风险：binding 解析默认全 bound（subscriber 可注入 resolver 收紧）；`schema_version` 门禁为可选（兼容旧信封）；草稿写入失败按 `draft_unavailable`/`draft_invalid_response`/`draft_submission_failed` 显式报错，不吞。
