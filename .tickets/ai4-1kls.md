---
id: ai4-1kls
status: closed
deps: []
links: [ai4-dp9t]
created: 2026-10-25T11:34:39Z
type: task
priority: 1
assignee: Frank Qi
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

- Registry 负责人明确接口冻结状态和剩余工作；
- 记录 `get_principal_contact` 的成功响应与 `principal_not_found`、`contact_missing`、`contact_disabled` 错误契约；
- 记录 email-service 使用 `service_role=email` 的只读权限边界；
- ai4-ndu0 能据此判断是否可以开始真实 MCP 联调。

## Notes

**2026-10-26T22:20:00Z 转交并结案（Frank Qi）**

转交记录：原 assignee `hanjiang`，经用户 2026-10-26 明确要求「hanjiang 那个转给我」后改为 `Frank Qi`，随后由我写入本节。身份核对：assignee `Frank Qi`、当前分支 `feature/frank-qi`、`git config user.name=Frank Qi`，三者一致。按 `AGENTS.md` 的属人修改权，转交时先改 `assignee` 再改内容。

**前提已消失。** 本票成立的理由是「`ai4-w4su` 当前仍为 open，导致联调前置状态不明确」。`ai4-w4su` 现已是 `closed`（assignee hanjiang，11 条验收全部勾选，2026-10-25 收尾）。`ai4-ndu0` 也已 `closed`：它把真实 Registry 适配器接进了 `email-service`，并记录了 `uv sync --locked` + 67 passed 的验证。本票要问的两件事——接口能不能用、`service_role=email` 的边界——`ai4-ndu0` 的实现已经用掉了。

**实测答案（2026-10-26，启动真实 Registry + 真实 Streamable HTTP MCP 探测）**

接口形状已经可用，逐个回答本票的 Requested action：

1. **`get_principal_contact` 的成功响应**：恰好 4 个键，没有别的。
   ```
   {"principal_id": "<原样回显>",
    "contact_email": "<存储值>",
    "status": "active",
    "contact_version": "contact:<principal_id>:<整数>"}
   ```
   `status` 恒为 `"active"`——非 active 的 principal 在读取时就被短路成 `contact_disabled`，走不到成功分支。

2. **稳定错误码**：`principal_not_found`、`contact_missing`、`contact_disabled`、`registry_unavailable` 四个，另有 `denied`。判定顺序是 `denied` → `missing_required_field` → `registry_unavailable` → `principal_not_found` → `contact_disabled` → `contact_missing`。注意 `contact_disabled` 先于 `contact_missing`：停用且无邮箱的 principal 报前者。

3. **`service_role=email` 的权限边界**：实测只能调两个工具——`get_principal_contact` 和 `health`。其余 `register_principal`、`register_workflow_agent`、`register_agent_instance`、`get_agent_registration` 一律 `denied`。对称地，`service_role=centre` 的 token 调 `get_principal_contact` 也是 `denied`，两个服务角色的只读面互不重叠。

4. **不需要真实凭证**：探测用的是临时 SQLite 与占位 token，未接触任何生产凭据。

**但联调前置并没有真的解除，原因不在 Registry 侧。** 错误码的形状对不上：Registry 把码放在纯文本 `Error executing tool get_principal_contact: <code>` 的尾部，`structuredContent` 为 `null`；而 `email-service` 的 `registry_client._result_payload` 只认 JSON 负载，解析失败后兜底 `registry_unavailable`。实测三个永久错误全部塌缩成 `registry_unavailable`，`NON_RETRYABLE_RECIPIENT_ERRORS` 分流因此永不命中。

这条缺口记在 [修正 email-service 对 Registry 联系人错误码的解析](ai4-dp9t.md)，不要求 Registry 改任何东西。本票不 blocked by 它，因为它问的是 Registry 侧状态，而 Registry 侧答案是「已完成」。

**结论：本票的两个问题已答完，前提已消失，结案。** 后续若还需要 Registry 配合，开新票指向具体工具，不要复用本票。
