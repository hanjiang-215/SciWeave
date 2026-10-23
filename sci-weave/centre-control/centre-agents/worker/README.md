# Task Agent Worker 角色

Worker 由 Gateway 以短生命周期进程启动，执行一次 fast-agent loop，并通过受控进程边界回报结果。

## 本地 DeepSeek 配置

复制 `.env.example` 为不提交的 `.env`，填写 `DEEPSEEK_API_KEY`。模型地址、模型名、持久目录和连接域均由该文件配置；源码不读取 `.env`，启动时由 uv 注入：

```bash
uv run --env-file .env --package sciweave-task-agent-worker sciweave-task-agent-worker
```

该命令只验证配置，不会输出 API Key 或发起模型请求。
