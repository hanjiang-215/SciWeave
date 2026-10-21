---
id: ai4-mqtq
status: open
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

遵循 Research Mapping 已确定的 SQLite 治理记录权威与 TerminusDB 精确图快照规则。复用已关闭的字段模型、候选治理和跨存储正式化规格；不新增 SDK 假设。若实现需要额外运行时依赖，先建立专门 fer 依赖任务，再声明来源、版本约束、用途、许可证/限制、验证方式及锁文件。

## Implementation Contract

- **代码位置：** 本票首先建立 `sci-weave/research-mapping/`，包含 `pyproject.toml`、独立 `uv.lock`、`.env.example`、`README.md`、`src/main.py`、`src/research_mapping/`、`tests/`。`requires-python` 使用 `>=3.11`，与仓库现有 Python 子项目一致。`main.py` 只组装服务；业务代码不得放在 `drafts/`。
- **基础模块：** 提供 `config.py`、`errors.py`、`canonical.py`、`domain.py`、`schema.sql`、`sqlite_store.py`、`terminus_store.py` 和 `formal_query.py`。SQLite 连接启用外键；本票只创建 Formal Query 所需的正式版本/当前指针最小治理结构，候选和审阅表由后续子票增量加入。
- **服务接口：** `FormalQueryService.get_current(mapping_domain_id)` 根据 SQLite 当前正式指针和对应正式治理记录，读取记录精确指向的 TerminusDB store/database/branch/commit。返回 `available`、`no_formal_revision`、`inconsistent` 或 `unavailable` 之一；仅 `available` 可含图内容，其余结果必须无候选正文，并带稳定 `reason_code`。
- **适配器 seam：** `TerminusStore.read_exact_snapshot(store_id, database, branch_id, commit_hash)` 返回显式 `confirmed`/`missing`/`unavailable` 结果；确认时包含实际 store/database/branch/commit 身份、规范内容 SHA-256 和图快照。未知结果或身份/摘要不匹配必须作为结构化失败交给查询服务，不能回退到分支最新 commit。后续子票只增量增加候选写入/正式快照读写方法，不把 HTTP 细节泄漏到应用服务。
- **共同持久化约定：** 业务 ID 为稳定字符串 UUID；时间为 UTC RFC 3339；内容摘要由排序键、紧凑分隔符的规范 JSON 计算 SHA-256。正式查询只接受 `succeeded` 正式化结果关联的当前 Formal MappingRevision。
- **配置与依赖：** `.env.example` 声明 `SCIWEAVE_MAPPING_SQLITE_PATH`、`SCIWEAVE_MAPPING_DOMAIN_ID`、`SCIWEAVE_MAPPING_TERMINUSDB_URL`、`SCIWEAVE_MAPPING_TERMINUSDB_DATABASE`、`SCIWEAVE_MAPPING_TERMINUSDB_STORE`、`SCIWEAVE_MAPPING_TERMINUSDB_TOKEN`。源码只读进程环境；由 `uv run --env-file .env ...` 注入配置。仅用标准库，不新增包；如确有依赖需求，先另建 fer 依赖票并记录来源、版本、用途、许可证/限制及验证命令。
- **验证命令：** README 记录 `uv sync --locked`、`uv run --env-file .env python -m unittest discover -s tests -v`，以及使用同一 `.env` 显式运行 `test_terminus_integration.py` 的命令。集成验证连接仓库固定的 TerminusDB 服务；测试地址从环境变量读取，不在代码/测试/文档中写死部署端口或凭据。

## Acceptance Criteria

- [ ] 项目骨架、标准库依赖声明、独立锁文件、环境样例、README、入口、包及测试目录按上述路径创建。
- [ ] 正常读取只返回 SQLite 当前指针、`succeeded` 结果和 Formal MappingRevision 共同确认的正式版本及精确 TerminusDB Commit 内容。
- [ ] 候选、未批准、未激活版本不能从普通查询路径返回；非 `available` 结果不得包含图正文。
- [ ] 无正式版本、指针/记录/Commit 不匹配、精确 Commit 不可读、内容摘要不符及存储结果未知均有结构化、可断言的结果；不返回候选、不静默回退。
- [ ] 使用临时 SQLite + Fake TerminusStore 覆盖成功、空正式视图、指针不一致、精确 Commit 缺失/错配和存储故障；仓库 TerminusDB 服务集成测试验证真实精确 Commit 读回。
- [ ] `uv sync --locked` 和 README 中声明的 `unittest` 命令通过；交付记录实际命令、输出摘要及集成服务是否运行，不把跳过集成测试写成通过。
