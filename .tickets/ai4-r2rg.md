---
id: ai4-r2rg
status: closed
deps: []
links: []
created: 2026-10-28T20:21:06Z
type: bug
priority: 3
assignee: hanjiang
---
# register_workflow_agent 的 principal_id 标为可选但实际必填

service.py:119-124：kind=endpoint 时 principal_id 缺失报 principal_required，但 schema 标注可选（B11）。调用方按 schema 构造会踩坑。

## Design

将 principal_id 在 endpoint 场景改为 schema 必填（centre 场景例外为空），并同步文档与错误信息。

## Acceptance Criteria

schema 与实际校验一致；缺 principal_id 时在 schema 层即被拦截；centre 场景行为不变；测试通过。


## Notes

**2026-10-29 / hanjiang**

已实现并验证（fix(registry): document principal_id per kind）：
- kind=endpoint 缺 principal_id 报 principal_required；kind=centre 必须为空。schema 保持可选（因 centre 需空），在工具描述与 service docstring 明确该规则。
- 测试：registry 16 passed（含 1 项新增，覆盖 endpoint 缺参报错 + centre 正常登记）。
