# Local MCP service cards

本目录保存研究员自定义 MCP 服务的描述卡片。卡片只注册服务能力和连接方式，不实现服务。`transport` 支持 `stdio` 和 `streamable-http`；stdio 卡片只允许使用 `uv`，项目目录通过 `project_dir_env` 指定，HTTP 地址通过 `endpoint.url_env` 指定。真实令牌只能通过环境变量提供。

**出厂不预置任何卡片**，只有这个 README。`load_mcp_registry` 对空目录返回「无本地覆盖」，不报错。

原先这里有一张 `local-literature.yaml`：只有一个 `search` 工具，背后没有任何服务，`project_dir_env` 指向不存在的项目目录。真实的文献检索已由 `libs/mcp-libs/literature-search/` 交付（arXiv 与 Crossref 双源），占位卡随之删除——留着只会让研究员以为它可用（`ai4-tj83`）。
