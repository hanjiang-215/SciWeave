---
id: ai4-orpg
status: open
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

Wiki 当前尚未由权威技术栈文档确定全部存储与部署边界；前置规格必须先确定这些实现约束。地图不预设与 Mapping 共用存储或服务，不指定未确认的 API/SDK/运行时依赖。后续依赖按 fer 任务确立并记录来源、用途、版本约束、许可证/限制、安装及验证方式；Python 服务遵循 Python + uv 和 SciWeave 子项目规范。

## Acceptance Criteria

- [x] Wiki 前置规格票、资源版本资格审核实现票和三张其他纵向实现子票均已创建在本地图下。
- [x] 四张实现票均阻塞于 Wiki 前置规格；资源审核、正式内容读取、提交/候选、审阅/正式化之间的必要顺序由 fer 依赖表达且无循环。
- [x] 前置规格明确资源版本进入正式引用的审核依据，以及 Wiki 自身跨存储正式化确认、失败状态、重试/恢复、查询权威和审计规则。
- [x] 每张实现子票均定义独立验证证据，并引用对应 Wiki 内容模型与治理规格。
- [x] 不预设 Mapping 与 Wiki 共用数据库、MCP、审核/审计链或跨域事务；未确定的部署与依赖决策留给规格/专门依赖任务。
- [x] 不修改 ai4-xup8 或把消息协作、Agent 套件纳入本地图范围。
