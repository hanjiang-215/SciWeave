# SciWeave 项目技术栈

> 本文是项目产品技术栈的权威记录。开发工具、vibe coding 依赖和本地验证服务的通用维护规则见 `docs/DEPENDENCIES.md`；两份文档均不记录开发机器状态、绝对路径、安装输出或真实凭据。

## 已确定技术栈

| 范围 | 技术 | 约束与用途 |
| --- | --- | --- |
| 后端服务 | Python + uv | Gateway、调度服务、领域服务和 MCP Server 统一使用 Python 开发；每个 Python 子项目以 `pyproject.toml` 声明元数据和依赖，使用 uv 解析、同步、运行并提交 `uv.lock`。 |
| MCP | Python | MCP Server 与 MCP 客户端适配统一使用 Python；具体 SDK、版本和权限模型由对应 fer ticket 确定后写入子项目依赖清单。 |
| Web 前端 | Vue | 浏览器端 Web 应用统一使用 Vue；具体 Vue 版本、构建工具、状态管理和组件库由前端实现 ticket 确定。 |
| 服务状态存储 | SQLite（MVP） | Gateway MVP 使用 Python 标准库 `sqlite3` 保存平台执行状态；不用于替代 fast-agent 的运行时会话文件。 |
| Agent 运行时 | fast-agent-mcp | Gateway 后续通过 Runtime Adapter 接入；具体版本和锁定方式由 `ai4-o806` 决定。 |

## 子项目结构

```text
sci-weave/<子项目>/
├── src/
│   ├── main.py         # 子项目启动入口
│   └── <模块名>/        # 产品业务代码
├── tests/             # 自动化测试
├── pyproject.toml     # Python 项目和工具配置（Python 子项目）
├── .env             # 本地环境变量，不提交
└── .env.example     # 环境变量名称和示例值，可提交
```

- 服务和 MCP 子项目必须遵守上述 Python 结构；项目目录名表达部署角色，`src/<模块名>/` 使用简洁职责名。
- `pyproject.toml` 是 Python 标准项目配置，不绑定管理工具；本项目统一使用 uv 读取该配置、生成并提交 `uv.lock`、同步环境与运行项目。
- 前端 Vue 子项目使用自身的 `package.json`、锁文件、`src/` 和测试目录；真实 `.env` 同样不得提交。
- 所有路径、监听地址、端口、令牌、数据库位置和外部服务地址通过环境变量提供，不能硬编码进源码或测试。
- 新增或升级依赖前，必须先有 fer ticket，随后在子项目清单和锁文件中声明，并在对应 ticket 回写来源、用途、许可证和验证结果。

## 已确定工具

- Python 子项目统一使用 uv 管理虚拟环境、依赖同步、命令执行与 `uv.lock`；`pyproject.toml` 仍是工具无关的 Python 项目配置。

## 未确定项

- Vue 版本、构建工具、测试工具和组件库。
- 生产部署、容器编排、密钥管理和 CI。
