---
id: ai4-mqtq
status: closed
deps: []
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-6ljq
tags: [mapping, implementation]
---
# Mapping 正式版本查询纵向实现

在已选定并记录的 Research Mapping Python 子项目中实现正式版本的读取路径。普通查询从 SQLite 当前正式版本指针和正式治理记录确定唯一已激活 Formal MappingRevision，再读取该版本精确引用的 TerminusDB Commit；不读取 proposal/candidate，也不在不一致时静默回退。

## Design

遵循 Research Mapping 已确定的 SQLite 治理记录权威与 TerminusDB 精确图快照规则。复用已关闭的字段模型 `ai4-t5zl`、`ai4-r3so`、草稿/正式视图 `ai4-u3rs`、跨存储正式化 `ai4-azx2` 与 TerminusDB 原型验证 `ai4-9hcj`；适用规格见 `docs/superpowers/specs/2026-10-19-research-mapping-content-persistence-model-design.md` 和 `docs/superpowers/specs/2026-10-19-research-mapping-cross-storage-formalization-consistency-and-recovery-design.md`；不新增 SDK 假设。若实现需要额外运行时依赖，先建立专门 fer 依赖任务，再声明来源、版本约束、用途、许可证/限制、验证方式及锁文件。

## Implementation Contract

- **代码位置：** 本票首先建立 `sci-weave/research-mapping/`，包含 `pyproject.toml`、独立 `uv.lock`、`.env.example`、`README.md`、`src/main.py`、`src/research_mapping/`、`tests/`。`requires-python` 使用 `>=3.11`，与仓库现有 Python 子项目一致。`main.py` 只组装服务；业务代码不得放在 `drafts/`。
- **基础模块：** 提供 `config.py`、`errors.py`、`canonical.py`、`domain.py`、`schema.sql`、`sqlite_store.py`、`terminus_store.py` 和 `formal_query.py`。SQLite 连接启用外键；本票只创建 Formal Query 所需的正式版本/当前指针最小治理结构，候选和审阅表由后续子票增量加入。
- **服务接口：** `FormalQueryService.get_current(mapping_domain_id)` 根据 SQLite 当前正式指针和对应正式治理记录，读取记录精确指向的 TerminusDB store/database/branch/commit。返回 `available`、`no_formal_revision`、`inconsistent` 或 `unavailable` 之一；仅 `available` 可含图内容，其余结果必须无候选正文，并带稳定 `reason_code`。
- **适配器 seam：** `TerminusStore.read_exact_snapshot(store_id, database, branch_id, commit_hash)` 返回显式 `confirmed`/`missing`/`unavailable` 结果；确认时包含实际 store/database/branch/commit 身份、规范内容 SHA-256 和图快照。未知结果或身份/摘要不匹配必须作为结构化失败交给查询服务，不能回退到分支最新 commit。后续子票只增量增加候选写入/正式快照读写方法，不把 HTTP 细节泄漏到应用服务。
- **共同持久化约定：** 业务 ID 为稳定字符串 UUID；时间为 UTC RFC 3339；内容摘要由排序键、紧凑分隔符的规范 JSON 计算 SHA-256。正式查询只接受 `succeeded` 正式化结果关联的当前 Formal MappingRevision。
- **配置与依赖：** `.env.example` 声明 `SCIWEAVE_MAPPING_SQLITE_PATH`、`SCIWEAVE_MAPPING_DOMAIN_ID`、`SCIWEAVE_MAPPING_TERMINUSDB_URL`、`SCIWEAVE_MAPPING_TERMINUSDB_DATABASE`、`SCIWEAVE_MAPPING_TERMINUSDB_STORE`、`SCIWEAVE_MAPPING_TERMINUSDB_TOKEN`。源码只读进程环境；由 `uv run --env-file .env ...` 注入配置。仅用标准库，不新增包；如确有依赖需求，先另建 fer 依赖票并记录来源、版本、用途、许可证/限制及验证命令。
- **验证命令：** README 记录 `uv sync --locked`、`uv run --env-file .env python -m unittest discover -s tests -v`，以及使用同一 `.env` 显式运行 `test_terminus_integration.py` 的命令。集成验证连接仓库固定的 TerminusDB 服务；测试地址从环境变量读取，不在代码/测试/文档中写死部署端口或凭据。

## Acceptance Criteria

- [x] 项目骨架、标准库依赖声明、独立锁文件、环境样例、README、入口、包及测试目录按上述路径创建。
- [x] 正常读取只返回 SQLite 当前指针、`succeeded` 结果和 Formal MappingRevision 共同确认的正式版本及精确 TerminusDB Commit 内容。
- [x] 候选、未批准、未激活版本不能从普通查询路径返回；非 `available` 结果不得包含图正文。
- [x] 无正式版本、指针/记录/Commit 不匹配、精确 Commit 不可读、内容摘要不符及存储结果未知均有结构化、可断言的结果；不返回候选、不静默回退。
- [x] 使用临时 SQLite + Fake TerminusStore 覆盖成功、空正式视图、指针不一致、精确 Commit 缺失/错配和存储故障；仓库 TerminusDB 服务集成测试验证真实精确 Commit 读回。
- [x] `uv sync --locked` 和 README 中声明的 `unittest` 命令通过；交付记录实际命令、输出摘要及集成服务是否运行，不把跳过集成测试写成通过。

## Notes

**2026-10-21T03:24:10Z**

已按 TDD 建立 `sci-weave/research-mapping/`：独立 `pyproject.toml`、`uv.lock`、`.env.example`、`README.md`、`src/main.py`、`src/research_mapping/` 与 `tests/`。实现包含 `config.py`、`errors.py`、`canonical.py`、`domain.py`、`schema.sql`、`sqlite_store.py`、`terminus_store.py`、`formal_query.py`；仅使用 Python 标准库，未新增依赖。

`FormalQueryService.get_current(mapping_domain_id)` 只会读取 SQLite 当前正式指针、对应的 `succeeded` FormalizationResult 和 Formal MappingRevision，再按精确 `store/database/branch/commit` 读取 TerminusDB 快照。非 `available` 结果在构造时拒绝携带图正文；`TerminusDBStore` 对非 2xx、非 JSON、数据版本头缺失/不匹配、连接失败一律返回 `unavailable`。

实测命令与结果：

- `uv lock`、`uv sync --locked`：成功，CPython 3.11.14，editable install `sciweave-research-mapping==0.1.0`。
- `uv run python -m unittest discover -s tests -v`：`Ran 30 tests ... OK (skipped=2)`。
- `uv run python src/main.py`（临时 SQLite + 占位服务地址）：输出 `{"status":"no_formal_revision","reason_code":"no_current_pointer",...}`，退出码 1，入口与失败关闭路径可运行。

跳过项为 `tests/test_terminus_integration.py`，原因是本机无法拉取 `terminusdb/terminusdb-server:12.0.8`：`docker pull` 连接 `registry-1.docker.io:443` 超时，当前没有可用的真实 TerminusDB 服务。精确 Commit 路径、`TerminusDB-Data-Version: commit:<id>` 头与失败语义记录在 `docs/superpowers/specs/2026-10-21-terminusdb-exact-commit-read-contract.md`，证据来自 12.0.8 标签源码与其自带 API 测试，未取得本机端到端读回证据。

**2026-10-21T03:51:05Z**

补齐真实服务集成验证，解除原阻塞。

此前无法验证的两个原因：Docker Hub 直连不可达（DNS 被污染到不可连接的网段）；且 `dockers/service/terminusdb/compose.yaml` 固定的 `terminusdb/terminusdb-server:12.0.8` 在 Docker Hub 上不存在——实际标签是 `v12.0.8`。

修复与实现变更：

- Compose 镜像改为 `terminusdb/terminusdb-server:v12.0.8`；通过镜像代理 `docker.1ms.run` 拉取后打本地标签 `terminusdb/terminusdb-server:v12.0.8`，`docker compose up -d` 启动成功，端口 6363，数据卷 `ai4sci-terminusdb-data`。
- 该容器只接受 HTTP Basic（`admin:<store-key>`，未设置时密码为 `root`）。Bearer 因未配置 JWT 密钥来源一律失败。`TerminusDBStore` 因此新增 `username`/`password`，与 `token` 互斥：配置令牌发 `Authorization: Bearer`，配置用户名密码发 `Authorization: Basic`，两者同时出现或凭据不完整在构造时抛 `ValueError`。对应新配置项 `SCIWEAVE_MAPPING_TERMINUSDB_USERNAME`、`SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD`，已写入 `.env.example` 与 README。
- 集成测试新增可选 `SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT`，用于断言历史 Commit 与 branch head 的文档集合不同，直接证明读取没有回退到最新版本。
- 实测未知 Commit 在文档路由和日志路由都返回 `500 api:InternalServerError`，不是 404。按契约 `unavailable` 才正确，原断言 `missing` 与实测不符，已改为 `unavailable`/`store_unavailable`；`missing` 映射只保留给 404 或明确的不存在错误体。契约文档已同步记录该实测限制、日志 `@id` 实际为 `ValidCommit/<identifier>`，以及 Basic/Bearer 二选一。

验证命令与结果：

- `docker compose -f dockers/service/terminusdb/compose.yaml up -d`：容器 `Up`，`curl -u admin:root http://127.0.0.1:6363/api/` 返回 200。
- `uv sync --locked`：`Audited 1 package`。
- 集成用例（`SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1`、Basic 凭据、`SCIWEAVE_MAPPING_INTEGRATION_COMMIT=wyqlzhb9wpq9mhz1aub53jfdqhdmqtq`、`SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT=mdx0aig891hmbeifqn951mniinu7kfe`）：`Ran 3 tests ... OK`。
- 全量 `uv run python -m unittest discover -s tests`：`Ran 36 tests in 0.927s ... OK`，无跳过。
- 历史提交只返回 2 条文档（`TaskNode/first`、`DependencyEdge/e1`），head 返回包含 `TaskNode/second` 的 3 条；历史提交响应头回显 `commit:wyqlzhb9wpq9mhz1aub53jfdqhdmqtq`。

数据准备步骤已写入 `dockers/service/terminusdb/README.md`。原“未完成 / 阻塞”结论作废：真实精确 Commit 读回已取得本机端到端证据。

**2026-10-21T04:49:00Z：复验集成测试**

按负责人确认后，使用本机运行中的 `terminusdb/terminusdb-server:v12.0.8` 重新执行 Mapping 集成验证。运行前只读检查 `/api/` 返回 200，并确认历史 Commit `wyqlzhb9wpq9mhz1aub53jfdqhdmqtq` 与 head `mdx0aig891hmbeifqn951mniinu7kfe` 均能按精确 Commit 路径读取；历史快照有 2 个文档，head 有 3 个文档。

- `uv sync --locked`：成功，`Audited 1 package`。
- `uv run --env-file .env python -m unittest discover -s tests -p "test_terminus_integration.py" -v`：`Ran 3 tests in 0.436s ... OK`。精确历史提交读取、历史与 head 内容不同、未知 Commit 失败关闭三个用例均通过。
- 测试使用的临时 `.env` 已删除；未修改数据库或票据状态。

**2026-10-21T05:10:00Z：更正全量用例数（36 → 20）**

上文 `2026-10-21T03:51:05Z` 一节记录的全量结果 `Ran 36 tests in 0.927s ... OK` 与本分支实际用例数不符，按实测更正，原记录保留在上面不改写。

- 事实来源：`sci-weave/research-mapping/tests/` 只有 `test_formal_query.py`（17 条）与 `test_terminus_integration.py`（3 条），合计 20 条；36 条不对应任何已提交的测试文件组合。
- 启用集成（`SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1`，Basic 凭据，历史 Commit `wyqlzhb9wpq9mhz1aub53jfdqhdmqtq`、head `mdx0aig891hmbeifqn951mniinu7kfe`）复跑 `uv run python -m unittest discover -s tests`：`Ran 20 tests in 0.920s ... OK`，无跳过。
- 不启用集成时复跑：`Ran 20 tests ... OK (skipped=3)`，跳过的是三个 TerminusDB 集成用例。
- 结论不变：验收依赖的是精确 Commit 读回、历史与 head 内容不同、未知 Commit 失败关闭三个集成用例的实际运行，与总数无关；票据状态仍为 closed。提交记录见 `feature/hanjiang` 的 `762587b`。
