# email-service

独立的通知意图投递服务核心。首版只提供 `human_notification_intent` 的 schema 校验、SQLite 状态持久化、`dedupe_key` 幂等和可替换发送端口；不绑定 SMTP、Redpanda 或第三方邮件 SDK。

## 验证

```bash
uv sync
uv run --env-file .env pytest -q
uv run --env-file .env python -m compileall -q src tests
```

生产配置通过 `.env` 提供；仓库只提交 `.env.example`。
