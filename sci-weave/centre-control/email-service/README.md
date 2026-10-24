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

## 验证

```bash
uv sync
uv run --env-file .env pytest -q
uv run --env-file .env python -m compileall -q src tests
```
