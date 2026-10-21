---
id: ai4-orpg
status: closed
deps: []
links: []
created: 2026-10-20T08:31:16Z
type: epic
priority: 1
assignee: hanjiang
parent: ai4-xup8
tags: [wayfinder:map, wiki, implementation]
---
# LLM-Wiki 持久化与正式化实现地图

在 Wiki 领域独立边界内组织规格前置与可验证实现工作；本票是实施索引，不替代领域规格，也不包含产品源码。

## Design

本地图仅覆盖 LLM-Wiki 实施，与 Research Mapping 分开维护存储、管理 MCP、领域校验和审计链；两个领域之间只使用显式稳定 ID/版本 ID 弱引用，不设计跨域原子提交。首先完成 Wiki 持久化与正式化前置规格，再推进资源版本资格审核、正式内容读取、提交/候选、审阅/正式化四个纵向实现切片。

**固定实施方案：** 独立 Python 子项目 `sci-weave/llm-wiki/`，与 Research Mapping 分开部署和演进；本项目维护自己的 `pyproject.toml`、`uv.lock`、`.env.example`、`README.md`、`src/main.py`、`src/llm_wiki/` 和 `tests/`。Python 版本下限按仓库现有子项目采用 `>=3.11`。首版只实现领域应用服务和存储适配器，不实现 MCP、Web API、消息消费者、Mapping/Wiki 共享包或跨域事务。

**数据和存储边界：** Wiki 独立 SQLite 保存治理记录、资源资格审核、正式指针、审计索引与正式化状态；Wiki TerminusDB Store 保存不可变 WikiDocument/WikiRevision、Resource/ResourceVersion、RawArtifact、Resource Reference 内容快照和精确 Commit。SQLite 不复制文档或资源正文。Wiki 与 Mapping 各自拥有数据库、Store、校验与审计链，只通过稳定 ID/版本 ID 弱引用，不共享存储或建立跨域外键。

**首版依赖：** 仅使用 Python 标准库及仓库已有 TerminusDB 本地验证服务；SQLite 使用 `sqlite3`，TerminusDB 经可替换 `TerminusStore` HTTP 适配器访问，单测使用 Fake。不得预设 SDK、ORM、Web 框架、迁移工具、身份服务或其他未确认运行时依赖；若实现确需增加依赖，必须先建立 fer 依赖票并记录来源、版本约束、用途、许可证/限制、安装和验证命令，再更新项目清单和锁文件。

**纵向边界：** `ai4-vczt` 先建立 Wiki 子项目骨架、SQLite 基础设施、TerminusStore seam 和资源资格审核/查询；`ai4-91tk` 增加正式内容查询；`ai4-txhf` 增加完整文档与引用接纳、隔离候选；`ai4-jdjx` 增加固定候选审阅、Owner 决策、正式化和恢复。稳定服务接口仅作为内部应用边界，不承诺外部网络 API。资源审核必须由可信组合边界提供可验证的 actor/authority context；没有可验证授权时拒绝作出资格决定，不以自由文本或自报角色代替验证。

## Acceptance Criteria

- [x] Wiki 前置规格票、资源版本资格审核实现票和三张其他纵向实现子票均已创建在本地图下。
- [x] 依赖顺序保持为前置规格 → 资源审核 → 正式内容读取 → 候选提交 → 候选审阅/正式化；`fer dep cycle` 无循环。
- [x] 领域规格明确资源版本审核依据与 Wiki 跨存储正式化、失败状态、重试/恢复、查询权威和审计规则。
- [x] 每张实现子票引用对应 Wiki 内容模型/治理规格，并具有成功、拒绝/失败和结果未知的可执行验证要求。
- [x] 固定独立 Python 子项目 `sci-weave/llm-wiki/`、标准库 + uv、SQLite 治理与 TerminusDB 内容边界、资源审核授权 seam、环境变量及本地服务验证方式；不增加未经确认的 SDK 或运行时依赖。
- [x] 不预设 Mapping 与 Wiki 共用数据库、MCP、审核/审计链或跨域事务；不修改 ai4-xup8，也不把消息协作、Agent 套件纳入本地图范围。

本票验收用于确认 Wiki 实施地图及其契约已收敛；子票代码、测试和实际运行证据完成后，才代表实现完成。

## Notes

**2026-10-21T03:03:59Z**

验收核查（2026-10-21）：前置规格 ai4-7xtf 已关闭；四张实现子票 ai4-vczt、ai4-91tk、ai4-txhf、ai4-jdjx 的 parent 均为 ai4-orpg，依赖为 7xtf <- vczt <- 91tk <- txhf <- jdjx，无循环。三张子票引用 Wiki 内容模型、候选治理与资源审核跨存储正式化规格文件，并含成功、拒绝与结果未知的验证要求。未修改 ai4-xup8，未引入共享存储或跨域事务。子票代码与运行证据完成后才代表实现完成。
