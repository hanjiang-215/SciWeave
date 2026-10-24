# email-service

受鉴权的通知受理服务。调用方通过官方 Python `mcp` SDK 的 Streamable HTTP 提交一条合法的 `human_notification_intent`。服务用注入的 `RecipientResolver` 按 `principal_id` 解析收件人，写入自己的投递库后返回 `accepted_for_delivery`，再由注入的发送端口投递。调用方之后只能用 `get_notification_status` 查看自己提交的投递状态。

监听地址、端口、令牌、投递库、审计库和公共邮箱都来自环境变量。应用代码只读进程环境，不读取 `.env`。访问账本使用共享的 `sciweave-audit-trail`，与投递库不是同一个库。本服务不连接真实 SMTP，不使用第三方邮件 SDK，也不消费 Redpanda。进程入口里的解析和发送端口是未绑定占位，测试注入 Fake。

## 安装

在本目录执行：

```bash
uv sync
```

## 配置

复制 `.env.example` 为 `.env`，再按本地部署修改路径、监听地址、令牌和公共邮箱。`.env` 不提交。

## 启动

```bash
uv run --env-file .env python src/main.py
```

MCP 路径是 `/mcp`，需要 bearer token。未认证的 `GET /health` 只返回 `status`、服务名和 API 版本。

不能发送的通知记成可查询终态，不调用发送端口，也不自动重试。缺少必填字段、未配置的 `notification_kind`、非 `1` 的 `schema_version`、HTML、附件、超过 200 字的主题、超过 4000 字的正文、敏感内容，以及调用方传入的 From、SMTP 或凭据，状态为 `invalid`。联系人缺失、禁用、不存在，或调用方地址与解析结果不一致，状态为 `permanent_failure`，工具错误码分别为 `contact_missing`、`contact_disabled`、`principal_not_found`、`address_mismatch`。投递记录写不进去时返回 `storage_unavailable`，并且不发信。发件信息只来自 `SCIWEAVE_EMAIL_*`。

## 验证

```bash
uv sync
uv run --env-file .env pytest -q
uv run --env-file .env python -m compileall -q src tests
```
