---
id: ai4-1kls
status: closed
deps: []
links: []
created: 2026-10-25T11:34:39Z
type: task
priority: 1
assignee: hanjiang
parent: ai4-ndu0
tags: [registry, email-service, coordination]
---
# 确认 Registry MCP 接口冻结并解除 email-service 联调前置

## Question

email-service 适配器工单 ai4-ndu0 依赖 Registry 工单 ai4-w4su。Registry 的实现代码和测试记录已经存在，但 ai4-w4su 当前仍为 open，导致真实 MCP 联调前置状态不明确。请确认 Registry 的联系人查询接口是否已冻结，并完成交接。

## Requested action

- 确认 `get_principal_contact` 的 Streamable HTTP MCP 接口、响应结构和稳定错误码已冻结；
- 确认 `caller_type=service`、`service_role=email` 的只读开放面可供 email-service 使用；
- 若 Registry 已完成，请关闭 ai4-w4su 或记录关闭前剩余事项；
- 若仍有未完成工作，请列出阻塞项、预计完成条件和是否允许 email-service 先按现有契约联调；
- 不要求提供真实凭证，联调用占位 token `email-service-mcp-token`。

## Acceptance Criteria

- [x] Registry 负责人明确接口冻结状态和剩余工作；
- [x] 记录 `get_principal_contact` 的成功响应与 `principal_not_found`、`contact_missing`、`contact_disabled` 错误契约；
- [x] 记录 email-service 使用 `service_role=email` 的只读权限边界；
- [x] ai4-ndu0 能据此判断是否可以开始真实 MCP 联调。

## Notes

**2026-10-26 确认冻结并关闭（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

前置 `ai4-w4su`（Registry 登记与查询 MCP）已 closed，`ai4-ndu0`（email-service 通过 Registry 解析收件人）已 closed。实测核对 `sci-weave/centre-control/registry` 现状，接口已冻结：

- **`get_principal_contact` 权限面**：`service.py` 中仅 `caller_type == "project_owner"` 或 `caller.service_role == "email"` 可调用，其余 `denied`。email-service 以 `service_role=email` 只读调用联系人，无登记/状态变更工具权限。
- **成功响应**：`{ "principal_id", "contact_email", "status", "contact_version" }`，`contact_version` 形如 `contact:<principal_id>:<版本号>`。
- **稳定错误码**：`principal_not_found`（主体不存在）、`contact_missing`（主体存在但无邮箱）、`contact_disabled`（主体非 active）、`registry_unavailable`（存储故障）、`denied`（调用面不符）。
- **MCP 传输**：Streamable HTTP `/mcp`，官方 Python `mcp` SDK 实现；独立 `/health` 探针。
- email-service 侧 `RecipientResolver` 已按此契约实现并通过 `test_registry_client.py` 覆盖（67 passed）。

结论：Registry 联系人查询接口已冻结，`ai4-ndu0` 的真实 MCP 联调前置已解除，本票验收四项全部满足，置 closed。

