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

## 验证

```bash
cd sci-weave/research-mapping
uv sync --locked
uv run --env-file .env python -m unittest discover -s tests -v
uv run --env-file .env python src/main.py
```

集成测试默认跳过；显式运行需要仓库固定的 TerminusDB 12.0.8 服务、可读的数据库和一次已存在的 Commit：

```bash
SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1 \
SCIWEAVE_MAPPING_TERMINUSDB_USERNAME=admin \
SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD=<store-key> \
SCIWEAVE_MAPPING_INTEGRATION_COMMIT=<historical-commit> \
SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT=<branch-head-commit> \
uv run --env-file .env python -m unittest discover -s tests -p "test_terminus_integration.py" -v
```

`SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT` 可选；提供后会额外断言历史 Commit 与 branch head 的文档集合不同，用于证明读取没有回退到最新版本。跳过或缺少配置都不算集成验证通过。Windows PowerShell 可分别设置这些环境变量后再执行同一 `unittest` 命令。

本机 2026-10-21 已用仓库固定的 `terminusdb/terminusdb-server:v12.0.8` 容器完成真实读回：3 个集成用例通过。容器只接受 HTTP Basic（默认容器存储密钥即密码），因此用 `SCIWEAVE_MAPPING_TERMINUSDB_USERNAME` / `_PASSWORD` 而不是 JWT 令牌。

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
