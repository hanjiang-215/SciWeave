---
id: ai4-6ljq
status: open
deps: []
links: []
created: 2026-10-20T08:31:16Z
type: epic
priority: 1
assignee: hanjiang
parent: ai4-xup8
tags: [wayfinder:map, mapping, implementation]
---
# Research Mapping 持久化实现地图

组织 Research Mapping 已收敛领域规格之上的可验证实现工作；本票是实施索引，不替代领域规格，也不包含产品源码。

## Design

本地图只覆盖 Research Mapping 实施，不覆盖 LLM-Wiki。领域模型、候选治理与跨存储正式化语义以已关闭规格工单为准；实现按正式版本查询、候选提交、候选审阅、正式化与恢复四个纵向切片推进，并通过 fer 依赖表达顺序。

**固定实施方案：** 独立 Python 子项目 `sci-weave/research-mapping/`，采用 Python + uv；项目组根配置不适用，本子项目维护自己的 `pyproject.toml` 与 `uv.lock`。`src/main.py` 是组装和运行入口，业务代码位于 `src/research_mapping/`，测试位于 `tests/`。本轮只实现领域应用服务和存储适配器，不实现 MCP、Web API、队列消费者或 Mapping/Wiki 共享包。

**数据和存储边界：** SQLite（标准库 `sqlite3`）是治理事实、正式指针、审计索引和正式化状态的权威；TerminusDB 保存不可变 TaskNode/DependencyEdge 图快照和精确 Commit。SQLite 不保存图正文。Mapping 独立拥有自己的 SQLite 数据库、TerminusDB Store、校验器与审计链；与 Wiki 仅通过稳定 ID/版本 ID 弱引用，不共享存储或跨域事务。

**首版依赖：** 只允许 Python 标准库与仓库已固定的 TerminusDB 本地验证服务；通过可替换的 `TerminusStore` 接口封装 HTTP 调用，单元测试使用 Fake 实现，集成测试使用本地服务。不得假设 SDK、ORM、Web 框架或迁移依赖。新增第三方依赖前须有专门 fer 工单，记录来源、用途、版本约束、许可证/限制、安装和验证命令，并更新 `pyproject.toml` 与 `uv.lock`。

**纵向边界：** `ai4-mqtq` 先建立子项目骨架、SQLite schema/Store、TerminusStore seam 和只读 Formal Query；`ai4-6s53` 建立候选提交与图结构校验；`ai4-z0lb` 固定候选头并生成差异/影响审阅证据；`ai4-1qyc` 执行 Owner 决策后的正式化、SQLite 条件激活与恢复。内部接口以领域服务为调用边界，不对外承诺网络 API。

**运行和配置：** `.env.example` 至少声明 `SCIWEAVE_MAPPING_SQLITE_PATH`、`SCIWEAVE_MAPPING_DOMAIN_ID`、`SCIWEAVE_MAPPING_TERMINUSDB_URL`、`SCIWEAVE_MAPPING_TERMINUSDB_DATABASE`、`SCIWEAVE_MAPPING_TERMINUSDB_STORE`、`SCIWEAVE_MAPPING_TERMINUSDB_TOKEN`。源码只读环境变量；本地运行使用 `uv run --env-file .env ...`。测试使用内存/临时 SQLite；不得在源码、测试或文档依赖固定部署路径、监听端口或凭据。

## Acceptance Criteria

- [x] 四个纵向实现子票均创建在本地图下，分别覆盖正式版本读取、候选提交、候选审阅、正式化与恢复。
- [x] 子票间存在明确的阻塞依赖，且所有依赖可由 fer 查询，无循环。
- [x] 每张子票都引用适用的已关闭领域规格，并定义独立可运行的验证证据和失败边界。
- [x] 子票统一固定 Python `>=3.11` + uv、SQLite 与 TerminusDB 的职责，不引入未经确认的 SDK 或第三方运行时依赖。
- [x] 实施位置固定为 `sci-weave/research-mapping/`；环境配置、锁文件、测试替身和本地 TerminusDB 集成验证方式均已写入地图及子票。
- [x] 不修改 ai4-xup8 或将 Wiki、消息协作、Agent 套件纳入本地图范围。

本票验收用于确认实施地图及其契约已收敛；子票中的代码、测试和运行证据完成后，才代表实现完成。
