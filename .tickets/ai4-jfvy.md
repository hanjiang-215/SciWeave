---
id: ai4-jfvy
status: closed
deps: []
links: []
created: 2026-10-19T06:47:28Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# Agent Kit manifest 与模板覆盖规则

承接 Gateway 最小底座与 Agent Kit 交付地图；本票只解决一个实现前置决策，不直接编写产品代码。

## Design

## Question
Agent Kit 如何描述 profile、Skills、Hooks、工作流、MCP 服务、权限、环境变量、版本兼容和配置覆盖？需要明确平台模板与项目定制内容的边界、未授权能力的拒绝规则，以及同一套件在不同 Gateway 版本上的兼容策略。

## Acceptance Criteria

形成可实现的 Agent Kit manifest、目录结构、权限声明、版本兼容和配置覆盖规格；不包含真实凭据，并能支持后续 ZIP 打包。


## Notes

**2026-10-19T06:58:30Z**

2026-10-19：根据目标收敛，本阶段不实现 Agent Kit manifest、Skills/Hooks 模板和多套件定制，转入后续独立阶段。
