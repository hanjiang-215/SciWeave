---
id: ai4-pwgl
status: open
deps: []
links: []
created: 2026-10-28T20:21:06Z
type: bug
priority: 3
assignee: hanjiang
---
# registry register_principal 的 role 枚举不接受 service

registry/src/registry/service.py:109-110 role 仅允许 researcher/project_owner，返回 invalid_role；但 register_workflow_agent 的 principal_id 可直接用 service:xxx，语义不一致（B10）。

## Design

决定 service 角色是否纳入 principal 枚举，并与 workflow_agent 的 service 主体语义统一；若纳入需同步 schema 与看板/文档。

## Acceptance Criteria

服务主体可按既定语义登记，不再返回 invalid_role；与 register_workflow_agent 语义一致；相关测试通过。

