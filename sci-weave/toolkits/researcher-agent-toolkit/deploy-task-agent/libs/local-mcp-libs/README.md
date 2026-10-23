# Local MCP service cards

本目录保存研究员自定义 MCP 服务的描述卡片。卡片只注册服务能力和连接方式，不实现服务。`transport` 支持 `stdio` 和 `streamable-http`；stdio 卡片只允许使用 `uv`，项目目录通过 `project_dir_env` 指定，HTTP 地址通过 `endpoint.url_env` 指定。真实令牌只能通过环境变量提供。
