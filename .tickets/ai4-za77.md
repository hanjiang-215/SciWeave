---
id: ai4-za77
status: open
deps: [ai4-z3z4]
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

- [ ] 套件包含 Work Agent 骨架模板、Agent 定义模板、初始化脚本、使用说明四部分，结构写明
- [ ] 骨架模板含三组件（处置面 MCP、消息监听、Worker）与共享 SQLite、状态机、Worker Lease
- [ ] 明确模板基线是 `sci-weave/task-agent/` 的现有实现，不另写一套；并写明它需要的三处改造
- [ ] 明确套件不负责部署、不托管凭据、不包含中央侧组件
- [ ] 明确 `.env.example` 需要哪些变量（队列地址与消费者组、数据库位置、持久目录、领域 MCP 地址、草稿箱地址）
- [ ] 使用说明能让研究员在无额外帮助的情况下建出一个能连上中央队列、执行任务并把结果写成草稿的 agent

> 修订（2026-10-22）：上列四部分验收改为下面三条，旧条目不删除。

- [ ] 套件包含 skill、服务模板、libs。skill 教 Personal Agent 按样例改 Agent 定义并装进定义槽，不教改 Gateway
- [ ] libs 含状态机、Worker Lease、拉起子进程，并预置 fast-agent 卡片样例。服务模板是三进程壳，调用 libs 启动，不把 Gateway 再实现一遍
- [ ] 与 `centre-agents` 无 path 依赖。两个 gateway 进程用用户级自启动常驻；hooks 只在打开 harness 时检查并补启动

## Notes

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
