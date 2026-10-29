---
id: ai4-ytpp
status: closed
deps: []
links: []
created: 2026-10-29T02:55:02Z
type: chore
priority: 2
assignee: hanjiang
---
# email-service 猴补丁 FastMCP 私有 API，升级可能静默失效

S6：server._reject_undeclared_send_arguments 用 object.__setattr__ 改写 tool.fn_metadata.call_fn_with_arg_validation 并依赖 _tool_manager。升级后有静默不生效风险。改为在安装前校验属性存在、安装后校验补丁生效，否则启动即报错。

## Acceptance Criteria

1) 缺属性时启动 RuntimeError；2) 补丁未生效时 RuntimeError；3) 新增单元测试；4) 既有 email 测试全绿

