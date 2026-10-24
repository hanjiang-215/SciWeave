# email-service

受鉴权的通知受理服务。调用方通过官方 Python `mcp` SDK 的 Streamable HTTP 提交一条合法的 `human_notification_intent`。服务用注入的 `RecipientResolver` 按 `principal_id` 解析收件人，写入自己的投递库后返回 `accepted_for_delivery`，再由后台投递循环通过注入的发送端口发信。暂时失败会进入 `retryable` 并按退避重试；进程重启后继续未完成的 `pending`、超时的 `sending` 和 `retryable`，沿用原来的通知。调用方之后用 `get_notification_status` 查看投递状态。`researcher`、`project_owner` 和 `service` 只能查看自己提交的通知。`caller_type=operator` 可以按 `notification_id` 查看任何人提交的状态，但仍然看不到正文、凭据或原始发送错误。失败状态带 `error_summary`，只用稳定错误码，不回传发送端口的原始文本。没有调用方重试工具。

监听地址、端口、令牌、投递库、审计库、公共邮箱和重试参数都来自环境变量。退避、轮询和 sending 超时分别是 `SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS`、`SCIWEAVE_EMAIL_RETRY_MULTIPLIER`、`SCIWEAVE_EMAIL_RETRY_MAX_SECONDS`、`SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS`、`SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS`。应用代码只读进程环境，不读取 `.env`。访问账本使用共享的 `sciweave-audit-trail`，与投递库不是同一个库。本服务不连接真实 SMTP，不使用第三方邮件 SDK，也不消费 Redpanda。进程入口里的解析和发送端口是未绑定占位，测试注入 Fake。

## 安装

在本目录执行：

```bash
uv sync
```

## 配置

复制 `.env.example` 为 `.env`，再按本地部署修改路径、监听地址、令牌和公共邮箱。`.env` 不提交。`SCIWEAVE_EMAIL_TOKENS_JSON` 和 `SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON` 的 JSON 值必须整体用单引号包住；不加引号时 `uv --env-file` 会剥掉双引号，服务启动时报 `must be a JSON object`。

## 启动

```bash
uv run --env-file .env python src/main.py
```

MCP 路径是 `/mcp`，需要 bearer token。未认证的 `GET /health` 只返回 `status`、服务名和 API 版本。公共邮箱未配置时状态是 `not_configured`，HTTP 状态码是 503。认证后的 `health` 在访问账本不可用、投递库仍可用时整体为 `degraded`。

不能发送的通知记成可查询终态，不调用发送端口，也不自动重试。缺少必填字段、未配置的 `notification_kind`、非 `1` 的 `schema_version`、HTML、附件、超过 200 字的主题、超过 4000 字的正文、主题或正文里的控制字符（换行、回车、制表符除外），以及调用方传入的 From、SMTP 或凭据，状态为 `invalid`。13 个核心 `notification_kind` 对所有已认证调用方开放。额外类型写在 `SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON`，按 `caller_id` 列出；没配这个变量时只有那 13 个。投递服务不扫描正文里的凭据；不把凭据写进通知是撰写方的责任。联系人缺失、禁用、不存在，或调用方地址与解析结果不一致，状态为 `permanent_failure`，工具错误码分别为 `contact_missing`、`contact_disabled`、`principal_not_found`、`address_mismatch`。投递记录写不进去时返回 `storage_unavailable`，并且不发信。发件信息只来自 `SCIWEAVE_EMAIL_*`。

## 验证

```bash
uv sync
uv run --env-file .env pytest -q
uv run --env-file .env python -m compileall -q src tests
```
