# SciWeave LLM-Wiki

LLM-Wiki 的资源资格审核切片。它只处理一个精确 `ResourceVersion` 能否在记录的使用范围内被 Wiki 候选或正式内容引用，不审核 Wiki 文档正文，也不替代 Project Owner 的正式发布审核。

- SQLite 追加保存资源审核决定和审计事件，不复制 ResourceVersion 正文。
- 资格按精确 `resource_version_id` 计算；新的 ResourceVersion 不继承旧决定。
- 只有 Resource Owner 或经注入验证器确认授权的审核人可以作出决定；无法证明授权时维持 `pending` 并记录被拒尝试。
- 资源内容、来源、许可和署名等事实由 TerminusDB 提供；未知项显式保留，不能伪装成已确认。
- 每条决定记录当时校验的精确 `store/database/branch/commit` 位置和快照 SHA-256，便于日后审计。

## 目录

```text
src/main.py                       启动入口：组装服务，可选查询一个版本资格
src/llm_wiki/config.py            进程环境配置
src/llm_wiki/domain.py            版本快照、审核记录、资格与审计模型
src/llm_wiki/canonical.py         规范 JSON 与 SHA-256
src/llm_wiki/schema.sql           追加式审核与审计 DDL
src/llm_wiki/sqlite_store.py      仅插入和读取的 SQLite 存储
src/llm_wiki/terminus_store.py    精确版本读取 seam 与失败关闭适配器
src/llm_wiki/resource_review.py   ResourceReviewService
tests/                            标准库 unittest
```

## 配置

仓库只提交 `.env.example`；真实 `.env` 不提交。先把 `.env.example` 复制为 `.env` 并填入本机值。源码只读取进程环境，由 `uv run --env-file .env ...` 注入。

| 变量 | 用途 |
| --- | --- |
| `SCIWEAVE_WIKI_SQLITE_PATH` | 审核与审计 SQLite 文件路径 |
| `SCIWEAVE_WIKI_DOMAIN_ID` | 当前 LLM-Wiki 上下文 ID |
| `SCIWEAVE_WIKI_TERMINUSDB_URL` | TerminusDB 服务地址 |
| `SCIWEAVE_WIKI_TERMINUSDB_DATABASE` | 目标数据库名 |
| `SCIWEAVE_WIKI_TERMINUSDB_STORE` | TerminusDB URL 中对应的组织/Store 段 |
| `SCIWEAVE_WIKI_TERMINUSDB_TOKEN` | 可选访问令牌；与 Basic 凭据二选一 |
| `SCIWEAVE_WIKI_TERMINUSDB_USERNAME` | 可选 HTTP Basic 用户名（本机固定容器为 `admin`） |
| `SCIWEAVE_WIKI_TERMINUSDB_PASSWORD` | 可选 HTTP Basic 密码；本机固定容器默认为存储密钥 |
| `SCIWEAVE_WIKI_DASHBOARD_MODE` | 设置为 `1` 时启动只读看板来源端点，而不是一次性打印查询摘要 |
| `SCIWEAVE_WIKI_DASHBOARD_HOST` | 看板来源端点监听地址 |
| `SCIWEAVE_WIKI_DASHBOARD_PORT` | 看板来源端点监听端口，测试可用 `0` |
| `SCIWEAVE_WIKI_DASHBOARD_TOKEN` | 可选 Bearer 令牌；配置后来源端点要求只读认证 |
| `SCIWEAVE_WIKI_MCP_HOST` | 可选管理 MCP 监听地址；与 `SCIWEAVE_WIKI_MCP_PORT` 同时配置后启用管理端点 |
| `SCIWEAVE_WIKI_MCP_PORT` | 管理 MCP 监听端口，测试可用 `0` |
| `SCIWEAVE_WIKI_MCP_TOKENS_JSON` | 管理 MCP 启用时必须提供：token → actor_id 映射 |
| `SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON` | actor → 能力档位列表：`read` / `candidate_submit` / `candidate_review` / `formalize` / `centre` |
| `SCIWEAVE_WIKI_AUDIT_SQLITE_PATH` | 可选接口层审计 SQLite；配置后服务启动时必须打开并建表，否则拒绝启动 |

## Web 看板只读来源

设置 `SCIWEAVE_WIKI_DASHBOARD_MODE=1` 后，进程提供 `GET /api/dashboard/source/wiki`。该端点只调用 `WikiFormalQueryService` 的正式查询，并按精确 ResourceVersion 投影资格状态；正式正文不出域，候选只返回 Proposal/提交身份、状态和必要的精确引用资格。候选快照不可读时保留候选身份并显示不可用事实，不伪装成正式内容。`POST`、`PUT`、`PATCH`、`DELETE` 均返回 405。可配置 `SCIWEAVE_WIKI_DASHBOARD_TOKEN` 保护读取端点。

## 管理 MCP（对外管理接口，`ai4-w73z` 切片二）

同时配置 `SCIWEAVE_WIKI_MCP_HOST` 与 `SCIWEAVE_WIKI_MCP_PORT` 后，进程提供领域管理 MCP（Streamable HTTP，`POST /mcp`，`GET /health`）。工具一律经 `WikiFormalQueryService` 与 `WikiCandidateService` 调用，不直连领域存储：

- `get_formal_wiki(wiki_domain_id)`：正式内容只读查询，要求 `read` 或 `centre` 能力；
- `list_wiki_candidates(wiki_domain_id)`：读取领域内已持久化的候选提交（提交者、正式基准、Proposal 与状态），要求 `read` 或 `centre` 能力；
- `submit_wiki_candidate(document_change, idempotency_key)`：完整文档与引用集合的候选提交，要求 `candidate_submit` 或 `centre` 能力。

调用方身份从 `Authorization: Bearer <token>` 解析，按 `SCIWEAVE_WIKI_MCP_TOKENS_JSON` 映射为 actor_id；服务端按 `SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON` 执行能力档位校验，未授权返回稳定 `forbidden` 错误。配置 `SCIWEAVE_WIKI_AUDIT_SQLITE_PATH` 后，读调用记录 `attempted`（fail-open）、写调用记录 `invoked`/`completed`（写前 fail-closed），审计位于接口层，领域服务不重复接入。测试覆盖权限分层、审计双阶段、传输层身份注入与越权拒绝，见 `tests/test_management.py`。

## 验证

```bash
cd sci-weave/centre-control/research-wiki
uv sync --locked
uv run --env-file .env python -m unittest discover -s tests -v
uv run --env-file .env python src/main.py
```

集成检查默认跳过；显式运行需要仓库固定的 TerminusDB 12.0.8 服务和完整配置：

```bash
SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1 \
uv run --env-file .env python -m unittest discover -s tests -p "test_terminus_integration.py" -v
```

集成用例自建临时数据库（名称为 `<SCIWEAVE_WIKI_TERMINUSDB_DATABASE>_it_<随机后缀>`），写入一个 `ResourceVersion`，记录历史提交，再更新同一版本生成新的 branch head；结束后删除该数据库。它需要可建库、可写文档的凭据；跳过或缺少配置都不算集成验证通过。

验证记录（2026-10-22）：`uv sync --locked` 成功；`uv run --locked python -m unittest discover -s tests -v` 共 85 项全部通过；`uv run --locked python -m compileall -q src tests` 成功。真实 TerminusDB 12.0.8 显式集成命令 `uv run --locked python -m unittest discover -s tests -p 'test_*integration.py' -v` 共 12 项全部通过，覆盖资源资格精确查询、候选隔离与读回、正式快照、Owner 正式化、撤回后阻断激活和正式查询。新增闭环回归测试还验证资源批准 ID 变化后旧 Owner 决定被清除、`WikiReviewService` 记录当前批准下的新 Owner 决定、旧 operation ID 被拒绝而新 operation ID 才能完成正式化。

## 资格状态

`get_current_qualification(resource_version_id, requested_scope)` 返回：

| 状态 | 含义 |
| --- | --- |
| `pending` | 没有适用于该版本和范围的审核决定 |
| `approved` | 最近一项适用决定为批准；范围与限制随结果返回 |
| `rejected` | 最近一项适用决定为拒绝 |
| `revoked` | 最近一项适用决定为撤回 |

决定按 `decided_at` 和追加顺序读取；批准、拒绝与撤回都追加新记录，旧记录保持不变。没有可用审核决定时，`reason_code` 为 `no_effective_decision`。

## 适配器状态

`TerminusStore.read_resource_version(location, resource_version_id)` 读取一个精确不可变版本：

- `location` 是 `ResourceVersionLocation(store_id, database, branch_id, commit_hash)`，必须来自写入该版本时固定的治理记录，不能由版本 ID 反查。
- 读取复用 TerminusDB 的精确 Commit 文档路由，并要求响应头回显 `commit:<请求 hash>`、返回列表中恰好一个文档匹配版本 ID。
- 确认结果包含所属 Resource、`owner_id`、版本声明的 `content_checksum_value`，以及对匹配文档按规范 JSON 计算的快照 SHA-256。
- 返回列表中没有该版本时是 `missing`；未知 Commit 在本镜像上返回 500，按 `unavailable` 处理；任何无法确认身份的结果都不会变成 `confirmed`，也不回退到 branch head。
- `ResourceReviewService` 必须注入 `ExactVersionLocationSource`；没有位置记录时返回 `exact_version_location_unknown` 并维持 `pending`，不会批准。候选/正式快照的写入与位置记录由后续切片提供。

契约细节与真实服务证据见 [`docs/superpowers/specs/2026-10-21-terminusdb-exact-commit-read-contract.md`](../../docs/superpowers/specs/2026-10-21-terminusdb-exact-commit-read-contract.md)。
