---
id: ai4-mx7h
status: closed
deps: [ai4-eikj]
links: [ai4-o2n3]
created: 2026-10-23T02:28:34Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-o2n3
tags: [implementation, ready-for-agent, task-agent, work-agent, toolkit, multi-agent, fast-agent]
---
# agent-libs 标准资源与本地扩展

## Parent

研究员端侧 Task Agent 与 deploy-task-agent-skills 规格（ai4-o2n3）。

## What to build

提供平台标准 Agent 资源和研究员本地扩展能力。标准资源包括提示词、任务模式、校验器、结果格式化器和工作流辅助资源；研究员可以通过 `local-agent-libs` 增加自定义资源。资源加载需要有稳定命名、版本兼容、覆盖优先级和冲突错误语义，并能被 Agent 定义或工作流引用。

## Blocked by

- Agent 定义与工作流配置模型（ai4-eikj）

## Acceptance Criteria

- [ ] 标准 Agent 资源可以按名称和版本被合法定义引用。
- [ ] 本地资源可以扩展标准资源，且不会直接修改标准资源。
- [ ] 标准与本地资源同名时按规定优先级处理，并对不兼容版本返回稳定错误。
- [ ] 提示词、任务模式、校验器和结果格式化器至少各有一个可验证样例。
- [ ] 资源加载测试不依赖真实模型或部署服务。

## Notes

**2026-10-23T03:02:13Z**

2026-10-23：完成 agent-libs 标准资源与本地扩展。新增提示词、任务模式、校验器、结果格式化器和工作流辅助资源注册表，支持 local-agent-libs、版本解析、覆盖和稳定冲突错误。验证：agent-libs 4 tests passed，runtime 8 tests passed，git diff --check 通过。
