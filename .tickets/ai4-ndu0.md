---
id: ai4-ndu0
status: open
deps: [ai4-w4su]
links: []
created: 2026-10-25T10:00:03Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-f985
tags: [implementation, email-service, registry, notification, contact]
---
# email-service 通过 Registry HTTP 只读端点解析通知收件人


## Notes

**2026-10-25T11:12:05Z**

本轮 Wayfinder 结论（2026-10-25）：

- Registry 接入采用现有 Streamable HTTP MCP `/mcp`，不新增同能力的 REST 查询协议。RecipientResolver 只调用 `get_principal_contact`，不直连 Registry 数据库，也不调用登记或状态变更工具。
- email-service 增加 `SCIWEAVE_EMAIL_REGISTRY_URL` 和 `SCIWEAVE_EMAIL_REGISTRY_TOKEN`。URL 配置完整 MCP 地址；token 只放 email-service 自己的 `.env`，不进入端侧或共享配置。Registry 侧 token 身份必须是 `caller_type=service`、`service_role=email`。
- RecipientResolver 改为异步接口；通知受理和真实 Registry 查询走异步调用链。SQLite 短事务可以继续同步，后台邮件 dispatcher 不负责 Registry 查询。
- Registry 查询成功后才写入 `notification_delivery`。网络连接失败、超时、429、5xx、MCP 传输失败等暂时故障按可重试错误处理；401/403、token 无效和工具权限错误按永久配置错误处理；`principal_not_found`、`contact_missing`、`contact_disabled`、`address_mismatch` 保持永久失败。
- 术语边界确认：通知收件人身份仍是 `principal_id` 对应的主体；调用方附带的 `email` 只是对当前登记地址的断言，不构成第二种收件人身份。不一致时返回 `address_mismatch`。该澄清后续补入 GLOSSARY.md。
- 本票依赖 Registry 实现与查询 MCP 工具完成，已添加对 `ai4-w4su` 的依赖。适配器验收需覆盖成功解析、四类永久错误、网络可重试错误、401/403、最小工具权限、token 不出日志，以及临时 HTTP/MCP 服务测试。

本票仍是实现票，当前只完成方案收敛，未修改产品源码，未关闭本票。实现前还需按项目依赖规范确认依赖、更新 pyproject.toml/uv.lock，并补充 `.env.example`。
