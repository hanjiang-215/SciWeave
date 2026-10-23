# Custom MCP service template

此目录只存需要 Python 实现的自定义 MCP Server 子项目。每个服务独立维护 `pyproject.toml`、`uv.lock`、`src/main.py` 和 `tests/`，通过 `uv run --env-file .env ...` 启动。服务的连接注册放在 `../libs/local-mcp-libs/`，卡片不嵌入 Python 代码、真实令牌或机器私有路径。

可复制 `stdio-service/` 创建新服务。
