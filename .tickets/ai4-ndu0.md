---
id: ai4-ndu0
status: closed
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
- Registry 查询成功后才写入 `notification_delivery`。网络连接失败、超时、429、5xx、MCP 传输失败等暂时故障按 `registry_unavailable` 直接返回且不写入投递记录；401/403、token 无效和工具权限错误按 `registry_denied` 永久错误处理；`principal_not_found`、`contact_missing`、`contact_disabled`、`address_mismatch` 保持永久失败。
- 术语边界确认：通知收件人身份仍是 `principal_id` 对应的主体；调用方附带的 `email` 只是对当前登记地址的断言，不构成第二种收件人身份。不一致时返回 `address_mismatch`。该澄清后续补入 GLOSSARY.md。
- 本票依赖 Registry 实现与查询 MCP 工具完成，已添加对 `ai4-w4su` 的依赖。适配器验收需覆盖成功解析、四类永久错误、网络可重试错误、401/403、最小工具权限、token 不出日志，以及临时 HTTP/MCP 服务测试。

当时本票仍是实现票，尚未修改产品源码；后续实现边界和验证记录见下方。实现前需按项目依赖规范确认依赖、更新 pyproject.toml/uv.lock，并补充 `.env.example`。

## Confirmed implementation boundary

- 复用 email-service 已有的官方 Python `mcp` SDK（`>=1.30,<2`），通过 Registry 完整 `/mcp` 地址调用 `get_principal_contact`，不新增 REST 查询协议。
- `RecipientResolver` 和通知受理链路使用异步接口；邮件后台 dispatcher 继续使用现有线程模型，不负责 Registry 查询。
- `RecipientResolver` 对外只返回已确认的邮箱地址；`contact_version` 不进入当前投递状态模型。
- 新增 `SCIWEAVE_EMAIL_REGISTRY_URL`、`SCIWEAVE_EMAIL_REGISTRY_TOKEN` 和 `SCIWEAVE_EMAIL_REGISTRY_TIMEOUT_SECONDS`；Registry token 独立于 email-service 调用方 token，不写入真实配置。
- 所有收件人必须全部解析成功后才写入 `notification_delivery`；任一收件人失败则整条通知不受理、不发信。
- 暂时性 Registry/MCP 故障映射为 `registry_unavailable`，直接返回且不写入投递表；401/403 或权限错误映射为 `registry_denied`；Registry 稳定业务错误保持原错误码。

## Acceptance Criteria

- [x] 通过官方 MCP 客户端从 Registry `/mcp` 成功解析多个 `principal_id`，并仅在全部成功后受理通知。
- [x] `email` 仅作为当前 Registry 联系人的地址断言；不一致返回 `address_mismatch`。
- [x] 缺少 Registry 配置时服务启动校验失败；连接失败、超时、429、5xx 和 MCP 传输错误在受理时返回稳定错误，不写入投递记录。
- [x] Registry 的 `principal_not_found`、`contact_missing`、`contact_disabled`、401/403 和权限错误按约定映射，错误不暴露 token、响应正文或堆栈。
- [x] 配置、运行时依赖、锁文件和 `.env.example` 完整更新；不提交真实凭据。
- [x] 使用临时 HTTP/MCP 服务和 Fake sender 覆盖成功、部分收件人失败、永久错误、暂时错误、超时和 token 不出日志场景。
- [x] email-service 全量测试、编译检查和 `git diff --check` 通过。

### Implementation notes

**2026-10-26 实现记录（Frank Qi）**

- 使用现有官方 Python `mcp` SDK（`>=1.30,<2`）和运行时依赖 `httpx>=0.28,<1`（BSD-3-Clause，来源 PyPI/Encode HTTPX），通过 Registry Streamable HTTP MCP `/mcp` 调用 `get_principal_contact`。
- 新增 Registry URL、token 和超时环境变量；token 只从 email-service 环境读取，不写入日志、响应或仓库配置。
- 受理链路改为异步，全部收件人解析成功后才写入投递库；Registry 暂时错误直接返回，不进入邮件后台重试状态机。
- 验证命令：`uv sync --locked`、`uv run --locked --env-file .env.example pytest -q`（67 passed）、`env -u SCIWEAVE_EMAIL_RETRY_MULTIPLIER -u SCIWEAVE_EMAIL_RETRY_MAX_SECONDS -u SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS uv run pytest -q`（67 passed）、`uv run --locked --env-file .env.example python -m compileall -q src tests`、`git diff --check`。
