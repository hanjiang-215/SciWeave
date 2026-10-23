# SciWeave Research Mapping

Research Mapping 的正式版本查询切片。它只回答一个问题：某个 `mapping_domain_id` 当前被激活的 Formal MappingRevision 精确指向哪次 TerminusDB 图快照，以及该快照是否可以确认。

- SQLite 保存当前正式指针、Formal MappingRevision 和 FormalizationResult 的治理索引，不复制图正文。
- TerminusDB 保存 TaskNode / DependencyEdge 的不可变图快照；只按精确 `store/database/branch/commit` 读取。
- 未激活的 Commit、候选内容和“branch 最新版本”都不会被普通查询返回。

精确 Commit 读取契约见 [`TerminusDB 12.0.8 精确 Commit 读取契约`](../../docs/superpowers/specs/2026-10-21-terminusdb-exact-commit-read-contract.md)。

## 目录

```text
src/main.py                      启动入口：读取配置、组装服务、输出查询摘要
src/research_mapping/config.py   进程环境配置
src/research_mapping/domain.py   查询结果、版本记录与快照读取结果
src/research_mapping/canonical.py 规范 JSON 与 SHA-256
src/research_mapping/schema.sql  最小治理记录 DDL
src/research_mapping/sqlite_store.py 外键启用的 SQLite 治理存储
src/research_mapping/terminus_store.py 精确 Commit 读取 seam 与 HTTP 适配器
src/research_mapping/formal_query.py  FormalQueryService
src/research_mapping/review.py       固定候选差异预览与审核 Buffer
src/research_mapping/formalization.py Owner 批准、正式化与恢复
src/research_mapping/sqlite_store.py SQLite 治理记录与激活事务
src/research_mapping/terminus_store.py 精确 Commit 读取和候选/正式快照适配器
tests/                           标准库 unittest
```

## 配置

仓库只提交 `.env.example`；真实 `.env` 不提交。先把 `.env.example` 复制为 `.env` 并填入本机值。源码只读取进程环境，由 `uv run --env-file .env ...` 注入。

| 变量 | 用途 |
| --- | --- |
| `SCIWEAVE_MAPPING_SQLITE_PATH` | 治理记录 SQLite 文件路径 |
| `SCIWEAVE_MAPPING_DOMAIN_ID` | 当前 Research Mapping 上下文 ID |
| `SCIWEAVE_MAPPING_TERMINUSDB_URL` | TerminusDB 服务地址 |
| `SCIWEAVE_MAPPING_TERMINUSDB_DATABASE` | 目标数据库名 |
| `SCIWEAVE_MAPPING_TERMINUSDB_STORE` | TerminusDB URL 中对应的组织/Store 段 |
| `SCIWEAVE_MAPPING_TERMINUSDB_TOKEN` | 可选 JWT 访问令牌；与下面两项二选一 |
| `SCIWEAVE_MAPPING_TERMINUSDB_USERNAME` | 可选 HTTP Basic 用户名；本机固定容器用 `admin` |
| `SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD` | 可选 HTTP Basic 密码；本机固定容器默认为存储密钥 |
| `SCIWEAVE_MAPPING_DASHBOARD_MODE` | 设置为 `1` 时启动只读看板来源端点，而不是一次性打印查询摘要 |
| `SCIWEAVE_MAPPING_DASHBOARD_HOST` | 看板来源端点监听地址 |
| `SCIWEAVE_MAPPING_DASHBOARD_PORT` | 看板来源端点监听端口，测试可用 `0` |
| `SCIWEAVE_MAPPING_DASHBOARD_TOKEN` | 可选 Bearer 令牌；配置后来源端点要求只读认证 |
| `SCIWEAVE_MAPPING_MCP_HOST` | 可选管理 MCP 监听地址；与 `SCIWEAVE_MAPPING_MCP_PORT` 同时配置后启用管理端点 |
| `SCIWEAVE_MAPPING_MCP_PORT` | 管理 MCP 监听端口，测试可用 `0` |
| `SCIWEAVE_MAPPING_MCP_TOKENS_JSON` | 管理 MCP 启用时必须提供：token → actor_id 映射 |
| `SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON` | actor → 能力档位列表：`read` / `candidate_submit` / `candidate_review` / `formalize` / `centre` |
| `SCIWEAVE_MAPPING_AUDIT_SQLITE_PATH` | 可选接口层审计 SQLite；配置后服务启动时必须打开并建表，否则拒绝启动 |

## Web 看板只读来源

设置 `SCIWEAVE_MAPPING_DASHBOARD_MODE=1` 后，进程提供 `GET /api/dashboard/source/mapping`。该端点只调用 `FormalQueryService.get_current`，只投影当前已激活且精确 Commit 已确认的正式 TaskNode/DependencyEdge；候选分支、未激活 Commit 和不一致结果不会返回图内容。`POST`、`PUT`、`PATCH`、`DELETE` 均返回 405。可配置 `SCIWEAVE_MAPPING_DASHBOARD_TOKEN` 保护读取端点；令牌只由服务端校验，不写入快照。

## 管理 MCP（对外管理接口，`ai4-w73z` 切片一）

同时配置 `SCIWEAVE_MAPPING_MCP_HOST` 与 `SCIWEAVE_MAPPING_MCP_PORT` 后，进程提供领域管理 MCP（Streamable HTTP，`POST /mcp`，`GET /health`）。工具一律经 `FormalQueryService` 与 `MappingCandidateService` 调用，不直连领域存储：

- `get_formal_mapping(mapping_domain_id)`：正式内容只读查询，要求 `read` 或 `centre` 能力；
- `list_candidates(submission_id)`：读取指定提交的候选治理记录（提交者、领域、正式基准、Proposal 状态、candidate head 与摘要），要求 `read` 或 `centre` 能力；无记录时返回 `candidate: null`；
- `submit_candidate(change_set, idempotency_key)`：候选提交，要求 `candidate_submit` 或 `centre` 能力。

调用方身份从 `Authorization: Bearer <token>` 解析，按 `SCIWEAVE_MAPPING_MCP_TOKENS_JSON` 映射为 actor_id；服务端按 `SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON` 执行能力档位校验，未授权返回稳定 `forbidden` 错误。配置 `SCIWEAVE_MAPPING_AUDIT_SQLITE_PATH` 后，读调用记录 `attempted`（fail-open）、写调用记录 `invoked`/`completed`（写前 fail-closed），审计位于接口层，领域服务不重复接入。测试覆盖权限分层、审计双阶段、传输层身份注入与越权拒绝，见 `tests/test_management.py`。
```bash
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked python -m compileall -q src tests
```

单元测试使用临时 SQLite，不需要 `.env`。需要运行应用入口或连接真实 TerminusDB 时，再按 `.env.example` 提供配置并使用 `uv run --env-file .env ...`。

集成测试默认跳过；显式运行需要仓库固定的 TerminusDB 12.0.8 服务、可读的数据库和一次已存在的 Commit：

```bash
SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1 \
SCIWEAVE_MAPPING_TERMINUSDB_USERNAME=admin \
SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD=<store-key> \
SCIWEAVE_MAPPING_INTEGRATION_COMMIT=<historical-commit> \
SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT=<branch-head-commit> \
uv run --env-file .env python -m unittest discover -s tests -p "test_terminus_integration.py" -v
```

验证记录（2026-10-22）：`uv sync --locked` 成功；`uv run --locked python -m compileall -q src tests` 成功；`uv run --locked python -m unittest discover -s tests -v` 共 74 项，72 项通过、2 项因全量测试默认未设置历史 Commit 参数而跳过。随后显式提供本地服务中两个不同的已存在 Commit，再运行 `uv run --locked python -m unittest discover -s tests -p 'test_terminus_integration.py' -v`，4 项全部通过，包含历史快照与 branch head 差异验证。另运行真实服务整链命令 `uv run --locked python -m unittest discover -s tests -p 'test_mapping_service_terminus_integration.py' -v`，1 项通过，覆盖临时 SQLite 与真实 TerminusDB 的候选、审阅、Owner 批准、正式化和正式查询。故集成验证并非跳过；全量默认运行中的两项需注入历史 Commit 参数才会执行。

```bash
uv run --env-file .env python -m unittest discover -s tests -p "test_terminus_integration.py" -v
```

## 查询结果

`FormalQueryService.get_current(mapping_domain_id)` 返回以下状态之一：

| 状态 | 含义 | 是否含图正文 |
| --- | --- | --- |
| `available` | 指针、成功正式化结果、精确 Commit 身份与摘要一致 | 是 |
| `no_formal_revision` | 该领域还没有当前正式指针 | 否 |
| `inconsistent` | 指针、版本记录、成功结果、快照身份或摘要互相矛盾 | 否 |
| `unavailable` | 精确 Commit 缺失、存储不可达或响应无法确认 | 否 |

非 `available` 结果在构造时就会拒绝携带图正文，避免失败结果被误用为正式内容。

## 适配器边界

`TerminusStore.read_exact_snapshot(...)` 只返回 `confirmed`、`missing` 或 `unavailable`。HTTP 路径、数据版本头和响应解析都留在 `TerminusDBStore` 内；应用服务不感知 HTTP 细节。适配器对以下情况一律返回 `unavailable`：非 2xx 响应、非 JSON 响应、缺少或回显不匹配的 `TerminusDB-Data-Version`、连接失败。

鉴权只使用一种形式：配置 `SCIWEAVE_MAPPING_TERMINUSDB_TOKEN` 时发送 `Authorization: Bearer`；配置用户名和密码时发送 `Authorization: Basic`；两者同时出现或凭据不完整会在构造适配器时直接报错，避免发出无法核验的请求。

`missing` 只依据 HTTP 404 或明确的不存在错误体判定。固定的 12.0.8 容器对未知 Commit 返回 `500 api:InternalServerError` 而不是 404，这种响应无法区分“不存在”和“服务故障”，适配器按 `unavailable` 处理，不猜测为空快照。
