---
id: ai4-b4zb
status: open
deps: []
links: []
created: 2026-10-26T18:38:15Z
type: bug
priority: 2
assignee: hanjiang
tags: [gap, centre-control, toolkits]
---
# 标准 MCP 卡片与两套领域工具面漂移（ai4-ced7 的 0/4 验收）

ai4-ced7 已关闭但四条验收全未勾选：deploy-task-agent 的 libs/mcp-libs/research-mapping/mcp.json 声明 7 个工具，服务实际 11 个；research-wiki 卡片 8 个，服务实际 11 个。runtime/tests/test_standard_mcp_cards.py 的期望清单照抄卡片，因此永远绿。

## Acceptance Criteria

卡片与 TOOL_DEFINITIONS 对齐（11/11）。|测试改为从服务定义生成期望，而不是抄卡片。|重开或更正 ai4-ced7 的状态。

