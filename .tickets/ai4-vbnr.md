---
id: ai4-vbnr
status: open
deps: [ai4-9f7i, ai4-ebqx, ai4-e257, ai4-dy2x]
links: []
created: 2026-10-16T00:37:54Z
type: grilling
priority: 1
assignee: qiyueran
parent: ai4-ru15
tags: [wayfinder:grilling, product, ai4science]
---
# 中央协调 Agent 与审计体系

## Question
中央 Agent、项目负责人和其他审核者如何分工？需要在宏观层面决定：中央 Agent 负责哪些协调和预审工作，负责人如何进行最终审计，哪些操作需要人工批准，以及平台如何提供完整执行留痕。暂不讨论模型选择和权限系统实现。

## Acceptance Criteria

明确中央协调、人工审计、风险分级和可追溯记录的一级功能；形成平台治理边界。

## Notes

**2026-10-17T01:53:26Z**

边界修正：Central Agent 保持为一个 Agent，但配置独立的 Mapping 管理 MCP 和 Wiki 管理 MCP。两个管理 MCP 背后的 Buffer、TerminusDB、Revision、审核和审计链完全隔离；Central Agent 负责路由和各领域预审，不通过单个提交跨域修改。
