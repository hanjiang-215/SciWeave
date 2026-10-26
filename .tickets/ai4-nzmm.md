---
id: ai4-nzmm
status: open
deps: []
links: []
created: 2026-10-26T18:38:14Z
type: bug
priority: 2
assignee: hanjiang
tags: [gap, centre-control, coordinator]
---
# 协调服务没有 MCP 入口，根任务无法由项目负责人启动

docs/data-flow/message-delivery-recovery.md 与 ai4-9mf8 把 dispatch_root_task 描述为 PO 可调的领域 MCP 工具，实际只有 CoordinatorService.dispatch_root_task 一个 Python 方法，两套领域管理 MCP 都没有该工具，coordinator 也不提供 MCP server。根任务按设计不自动派发，因此首版根任务没有启动入口。

## Acceptance Criteria

在领域管理 MCP 增加 dispatch_root_task 并转发到协调服务，或立票明确延后并改文档措辞。|补测试覆盖 PO 身份与幂等。

