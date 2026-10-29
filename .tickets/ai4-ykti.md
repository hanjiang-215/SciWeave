---
id: ai4-ykti
status: open
deps: []
links: []
created: 2026-10-29T14:26:31Z
type: feature
priority: 1
assignee: Frank Qi
tags: [toolkit, suite-manifest, ready-for-agent]
---
# 建立声明式套件清单与平台能力模型

依据工具包项目级部署与 Harness 导出设计规格，为 Project Owner 与 Researcher 套件建立可解析、闭合的声明式清单和逐项平台能力模型。

## Design

来源规格：docs/superpowers/specs/2026-10-29-toolkit-project-deployment-and-harness-export-design.md。清单声明角色、能力边界、相对资源路径、环境变量、运行载荷、导出规则和平台状态；具体 schema 版本作为实现决策记录，不将 install/check shell 当公共契约。

## Acceptance Criteria

- [ ] 两套套件的清单都能解析并验证封闭字段集合。
- [ ] 清单声明 suite/version/role/actor/summary、能力上限、资源相对路径、所需环境变量及用途。
- [ ] 清单逐项声明平台状态 supported/manual/unsupported/unverified 与限制说明。
- [ ] 能力上限不得超过 actor 权限；缺失引用、未知状态和非法路径均明确报错。
- [ ] Schema 版本及兼容策略在实现中明确记录并有测试覆盖。
