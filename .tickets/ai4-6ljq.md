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

技术边界：遵循 Python + uv；SQLite 保存治理事实，TerminusDB 保存精确图快照。此地图不预设新的服务部署单元、API、TerminusDB 客户端 SDK 或额外运行时依赖。开始代码实现前需确定合规子项目位置；新依赖须先有 fer 任务，记录来源、用途、版本约束、许可证/限制和验证命令，并写入 pyproject.toml 与锁文件。

## Acceptance Criteria

- [ ] 四个纵向实现子票均创建在本地图下，分别覆盖正式版本读取、候选提交、候选审阅、正式化与恢复。
- [ ] 子票间存在明确的阻塞依赖，且所有依赖可由 fer 查询，无循环。
- [ ] 每张子票都引用适用的已关闭领域规格，并定义独立可运行的验证证据和失败边界。
- [ ] 子票记录 Python + uv、SQLite 与 TerminusDB 的职责约束，不臆造未确定 SDK 或额外运行时依赖。
- [ ] 子票明确在实现前确定部署角色/子项目位置，配置通过环境变量提供，测试不依赖固定部署端口。
- [ ] 不修改 ai4-xup8 或将 Wiki、消息协作、Agent 套件纳入本地图范围。
