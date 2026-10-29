---
id: ai4-lewg
status: open
deps: []
links: []
created: 2026-10-29T14:26:31Z
type: feature
priority: 1
assignee: Frank Qi
tags: [toolkit, project-runtime, ready-for-agent]
---
# 建立项目级 SciWeave 布局与忽略策略

依据工具包项目级部署与 Harness 导出设计规格，实现项目根下的 SciWeave 目录边界，区分 Harness 生成输入、项目运行实例、运行态数据与用户自定义定义。

## Design

来源规格：docs/superpowers/specs/2026-10-29-toolkit-project-deployment-and-harness-export-design.md。运行态、生成内容和秘密默认忽略；允许明确共享非秘密定义，不使用裸 * 屏蔽全部内容。

## Acceptance Criteria

- [ ] 在显式项目根初始化项目级 SciWeave 目录，目录职责与数据归属清楚且可验证。
- [ ] 默认忽略运行态、生成 runtime、服务注册文件与秘密。
- [ ] 可通过明确例外共享非秘密项目定义或模板。
- [ ] 测试覆盖忽略规则的默认忽略与显式放行行为。
- [ ] 文档说明项目根缺失时必须要求用户指定，不从当前目录或用户目录猜测。
