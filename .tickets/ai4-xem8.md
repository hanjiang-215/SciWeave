---
id: ai4-xem8
status: closed
deps: []
links: [ai4-he04, ai4-s12u]
created: 2026-10-21T12:49:00Z
type: feature
priority: 1
assignee: hanjiang
tags: [centre-control, buffer, terminusdb]
---
# 中央草稿箱的存储与审核契约

把 2026-10-21 讨论确定的草稿箱设计收敛成可实现的契约：一个 TerminusDB 数据库、两个命名空间、草稿文档字段、固定提交版本的审核语义和一套 MCP 工具。设计记录见 `docs/data-flow/draft-buffer.md`。

## Problem Statement

`sci-weave/centre-control/buffer/` 目前只有一行说明。Research Mapping、LLM-Wiki 都没有「尚未进入候选分支的内容」的落盘位置，也没有承载一审的服务。既有工单把这一步分别写在领域 SQLite 的 Buffer Submission 表里，与「草稿集中存放、由人一审、通过后由人调 MCP 写候选」的模型不一致。

## Solution

中央服务器上一个独立的 Python 子项目 `sci-weave/centre-control/buffer`，用 TerminusDB 作为存储，对外一套 MCP。它保存草稿正文与审核状态，不创建候选、不写领域存储、不发起执行。

一个数据库 `sciweave_draft_domain`，两个命名空间 `mapping` 与 `wiki`，审核人分别是任务节点负责人与 Wiki 负责人。命名空间是文档上的字段；审核人配置在命名空间配置记录上，不逐份草稿复制。

> 修订（2026-10-21）：原设计为两个数据库、三个命名空间，其中 `sciweave_draft_task_agent` 与 `task_agent_design` 随 Task Agent 端侧自持一并删除，依据工单「Task Agent 改由研究员端侧自持」。

## Design

### 工单规格与范围说明

本票当前有效决策以本文件中的 `Solution`、`Design` 和 `Acceptance Criteria` 为准：唯一数据库 `sciweave_draft_domain`、`mapping`/`wiki` 两个命名空间、人工一审、提交 Commit 固定。下方旧 Notes 及 `docs/data-flow/draft-buffer.md` 中的历史冲突清单用于记录讨论过程；其中“两个数据库/Task Agent 草稿”、待裁决既有票冲突和未定项不得覆盖本票已定范围。`mark_promoted` 由领域 MCP 调用方在候选创建后显式调用，记录候选 ID 与精确 Commit；不新增反向回调或强一致跨服务依赖。调用者身份沿用经认证的 MCP caller，不在 Buffer 新建人员目录。跨命名空间收件箱不属于首版；按 namespace 过滤即可。


- 类 `Draft`：`draft_id`、`namespace`、`kind`、`title`、`submitted_by`、`submitted_at`、`status`、`base_formal_revision_id`、`source_task_node_id`、`source_execution_record_id`、`payload`（`sys:JSON`）、`submitted_commit`、`reviewer_id`、`review_decided_at`、`review_reason`、`supersedes_draft_id`。
- 类 `NamespaceConfig`：`namespace`、`reviewer_ids`、`allowed_kinds`、`promotion_target`。
- `@key` 必须用 `Random`。`Lexical` 键遇到字段值中的 `/` 会百分号编码，`@id` 与生成 ID 不一致直接失败（本机 12.0.8 实测）。

### 状态机

```text
drafting → submitted → under_review → accepted → promoted
                     └→ rejected →（修订后重新 submitted）
任意非 promoted 状态 → abandoned
```

审核对象是提交时固定的 `submitted_commit`。提交后草稿正文仍可修改，但不改变本轮审核对象。

### MCP 工具

`create_draft`、`update_draft`、`submit_draft`、`list_drafts`、`read_draft`、`review_draft`、`mark_promoted`。写操作带幂等键；`review_draft` 重复调用返回首次结论。

### 已知存储限制

- GraphQL 支持按字段过滤与 `limit`/`offset`，不支持 `order_by`，排序在服务层做。
- 手写 WOQL 的 JSON-LD 形状易错，查询走 GraphQL。
- 权限按命名空间授予：两个命名空间同库，库级权限不足以区分，需在服务层按命名空间校验。

## Testing Decisions

- 以 MCP 工具调用为主要测试接缝，不检查私有函数或表访问。
- 使用临时命名空间或临时数据库，测试结束清理；不依赖固定端口与真实凭据。
- 覆盖：创建与修改草稿、提交固定 Commit、提交后修改不改变审核对象、按命名空间解析审核人、越权审核被拒、幂等重复审核、驳回后重新提交产生新版本、`promoted` 后只读。
- TerminusDB 行为验证使用仓库固定的 12.0.8 服务，单测用 Fake 存储。

## Acceptance Criteria

- [x] 一个数据库、两个命名空间与 `Draft`、`NamespaceConfig` 字段按本票实现，`@key` 使用 `Random`
- [x] 草稿提交固定精确 Commit；提交后修改正文不改变本轮审核对象
- [x] 审核人从命名空间配置解析并留档，越权审核被拒绝
- [x] `review_draft` 幂等，重复调用返回首次结论且不产生第二次决定
- [x] 草稿箱不创建候选、不写领域存储、不发起执行；`promoted` 只记录候选标识与 Commit
- [x] MCP 工具在临时数据库上的自动化测试通过，且不依赖固定端口或真实凭据

**2026-10-23T08:23:00+08:00**

负责人由 Frank Qi 转交给 hanjiang，原因：由 hanjiang 继续负责中央草稿箱（buffer）契约的实现与推进。

**2026-10-23T13:03:00+08:00**

身份归一：本票原负责人即当前操作者，负责人字段已统一为 `hanjiang`；保留上方历史转交记录以维护变更轨迹。

**2026-10-23 实施更新**

负责人重新核对当前 `Solution`/`Design` 后，将唯一数据库与两个命名空间视为现行要求；历史 Notes 中“两个数据库/三个命名空间”仅保留讨论历史。采用“人调领域 MCP 创建候选后调用 `mark_promoted`、身份取自认证 MCP caller、首版无跨命名空间收件箱”的最小方案，不建立 Buffer 到领域服务的回调或跨服务强一致依赖。设计输入为 `docs/data-flow/draft-buffer.md`，详细裁决已记于本票 Notes。

**2026-10-23 Buffer 实现与验证**

- 修复服务层提交、审核、晋级流程：审核结论留档，提交时固定精确 Commit，拒绝后修订生成新草稿身份，重复审核按幂等记录返回首次结论。
- stdio MCP 不把 `actor_id` 当作可信客户端参数；工具调用必须由可信宿主注入 `_trusted_actor_id`，入口将其覆盖到服务调用。裸 stdio 缺少该注入时显式拒绝；`create_draft` 的提交者也由宿主身份覆盖。
- TerminusDB 写入只接受响应中可确认的精确 Commit；超时、无 Commit 响应和异常结果均失败关闭，不返回伪造分支头。
- 验证：`uv sync --project sci-weave/centre-control/buffer --locked`、Buffer 12 项单元测试、`compileall` 和 `git diff --check` 均通过。

**2026-10-23 真实 TerminusDB 集成验证**

- 新增 `tests/test_terminus_integration.py`：在真实 TerminusDB 12.0.8（本机 `127.0.0.1:6363`）临时数据库上验证完整生命周期（create→submit→review accepted→mark_promoted）、精确 Commit 落库并可从分支日志读回、幂等重放不产生第二条记录、跨命名空间审核被拒；用例创建临时数据库并在清理阶段删除，凭据仅来自进程环境变量，不写入仓库。
- 适配过程中实测并修复 `TerminusDBDraftStore` 三处 12.0.8 语义问题：
  1. 请求头不能携带 `TerminusDB-Data-Version: schema/instance`（应返回 `Bad data version`），改为只在读取时依赖响应头确认快照版本；
  2. schema 中可空字段必须以 `Optional` 声明，否则插入 `null` 报 `required_field_does_not_exist_in_document`；
  3. 已存在文档重写必须走 `PUT`（带完整 `terminusdb:///data/...` @id），`POST` 会因 `DocumentIdAlreadyExists` 拒绝；`write` 现为「新增 POST + 更新 PUT」并按分支日志确认精确 Commit。
- 验证结果：`uv sync --project sci-weave/centre-control/buffer --locked`、Buffer 15 项测试（12 单测 + 3 集成）、`compileall`、`git diff --check` 全部通过。
- 验收标准 6「MCP 工具在临时数据库上的自动化测试通过」现已满足实时存储条件；MCP dispatch 层已由单测覆盖，集成层覆盖真实存储往返。

**2026-10-23 Streamable HTTP 传输升级**

- 新增 `src/draft_buffer/mcp_http.py`：配置 `SCIWEAVE_BUFFER_MCP_HOST` + `SCIWEAVE_BUFFER_MCP_PORT` 后，进程改在 `POST /mcp` 提供 MCP JSON-RPC（`initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`，支持批量），并保留 `GET /health` 健康检查。stdio 传输保留为默认路径，两套传输共享同一 `dispatch`。
- 认证与身份：HTTP 传输不信任请求体里的 `actor_id`；调用者身份从 `Authorization: Bearer <token>` 解析，按 `SCIWEAVE_BUFFER_MCP_TOKENS_JSON` 映射为 `actor_id` 后由服务端注入 `_trusted_actor_id`。缺失或未知令牌返回 HTTP 401；启用 HTTP 端点时令牌映射为必填，不允许匿名端点。客户端伪造的 `actor_id` 参数在注入时被清除。
- 新增 `tests/test_mcp_http.py` 覆盖回环地址与临时端口 `0`：无令牌/未知令牌 401、合法令牌 initialize 与工具调用、提交者身份被 Bearer 身份覆盖、命名空间越权审核拒绝、非 MCP 路径 404、PUT/PATCH/DELETE 405、畸形 JSON 返回 -32700、通知返回 202、配置必须 host/port/令牌成对出现。
- 验证：`uv sync --project sci-weave/centre-control/buffer --locked` 成功；`uv run --locked python -m unittest discover -s tests -v` 共 25 项（含 HTTP 传输 10 项、store 适配 3 项、dispatch 与服务状态 12 项），全部通过，集成用例默认跳过；`uv run --locked python -m compileall -q src tests` 成功；`git diff --check -- sci-weave/centre-control/buffer/` 无空白错误。
- 范围说明：HTTP 端点不新增任何固定监听地址或端口语义，监听地址与端口全部来自环境变量；本轮未改变草稿箱的存储、审核与幂等语义。领域管理 MCP（Mapping/Wiki 对外接口）契约与实现由 `ai4-w73z` 单独推进，本票不越权承接。

**2026-10-23 验收收尾与关闭**

- 逐条核对六项验收标准，均有实现与测试证据支撑，全部勾选：
  1. 唯一数据库、`mapping`/`wiki` 两命名空间、`Draft`/`NamespaceConfig` 字段与 `@key: Random` 由 `TerminusDBDraftStore.initialize_schema` 实现，`tests/test_store_adapter.py` 覆盖；
  2. 提交固定精确 Commit、修改不改变审核对象由 `submit_draft` 冻结 `submitted_commit` 保证，单测与真实集成（`test_full_draft_lifecycle_persists_exact_commit`）覆盖；
  3. 审核人按命名空间配置解析、越权拒绝由 `_authorize_namespace` 保证，单测与真实集成（`test_cross_namespace_review_is_rejected`）覆盖；
  4. `review_draft` 幂等由 `_mutate` 幂等键机制保证，单测与真实集成（`test_idempotent_create_and_review_replay_produce_no_second_records`）覆盖；
  5. 不创建候选、不写领域存储、`promoted` 只记录候选标识与 Commit 由 `_promote` 保证，单测 `test_candidate_promotion_records_exact_id_and_commit` 覆盖；
  6. MCP 工具自动化测试使用内存 Store 与回环/临时端口，不依赖固定端口或真实凭据；真实 TerminusDB 集成使用临时数据库并由用例清理。
- 收尾复验（2026-10-23）：`uv run --locked python -m unittest discover -s tests` 25 项通过（集成默认跳过）；以本机 `127.0.0.1:6363` + `admin:root` 运行 `tests/test_terminus_integration.py` 3 项全部通过；`compileall` 与 `git diff --check` 通过。
- 本票六项验收全部满足，状态置为 `closed`。



本票由 `docs/data-flow/draft-buffer.md` 收敛而来。该文件第 8 节列出的既有票冲突不由本票裁决：`ai4-mjku`、`ai4-hkdz` 把 Buffer Submission 放在领域 SQLite；`ai4-xrxw` 的状态链把中央预审写在提交上；`ai4-wd5l` 的顺序是「先接纳执行结果、再创建领域草稿」。三张票的负责人需要决定是否接受新模型的改写。

未定项见该文件第 9 节：`mark_promoted` 由谁调用、是否需要跨库统一收件箱、草稿与候选是否要求内容强一致、参与者身份来源。

**2026-10-21T13:08:28Z**

2026-10-21T21:10:00Z

范围收窄，依据「Task Agent 改由研究员端侧自持」(ai4-we38)：中央不再有 task-agent 服务和部署动作，因此不存在「Task Agent 声明式设计稿」这一类草稿。

需要修改的部分（本票仍由 Frank Qi 负责，正文修订随后进行）：

- 删除第二个数据库 `sciweave_draft_task_agent`。
- 删除命名空间 `task_agent_design`，命名空间只保留 `mapping` 与 `wiki`。
- 保留「两个数据库」表述中的 `sciweave_draft_domain` 为唯一数据库。
- 权限按库授予这条不再需要区分库，改为按命名空间授予。

本票其余部分（`Draft` 与 `NamespaceConfig` 字段、固定 `submitted_commit` 的审核语义、幂等审核、已知存储限制）不受影响。
