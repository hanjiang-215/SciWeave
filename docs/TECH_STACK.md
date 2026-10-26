# SciWeave 项目技术栈

> 本文是项目产品技术栈的权威记录。开发工具、vibe coding 依赖和本地验证服务的通用维护规则见 `docs/DEPENDENCIES.md`；两份文档均不记录开发机器状态、绝对路径、安装输出或真实凭据。

## 已确定技术栈

| 范围 | 技术 | 约束与用途 |
| --- | --- | --- |
| 后端服务 | Python + uv | Gateway、调度服务、领域服务和 MCP Server 统一使用 Python 开发；每个 Python 子项目以 `pyproject.toml` 声明元数据和依赖，使用 uv 解析、同步和运行。依赖锁文件按下面的“项目组”规则提交：独立子项目提交自身 `uv.lock`，同一项目组的多个子项目提交组级唯一 `uv.lock`。 |
| MCP | Python | MCP Server 与 MCP 客户端适配统一使用 Python。Owner 侧接入采用 **Streamable HTTP** 传输：Gateway 作为 MCP server，Task Owner 的 harness（Codex、Cursor 等）作为 MCP client 注册地址与令牌。HTTP 回环端点仅用于健康检查、本地调试和测试 seam，不作为 Owner 主通道。具体 SDK 版本由对应 fer ticket 确定后写入子项目依赖清单。 |
| Web 前端 | Vue 3.5 + Vite 7 + Pinia 3 | 浏览器端 Web 应用统一使用 Vue；版本按 `sci-weave/centre-control/web-ui/package.json` 固定：`vue ^3.5.22`、`vue-router ^4.5.1`、`pinia ^3.0.3`，构建用 `vite ^7.1.7`、`typescript ^5.9.3`、`vue-tsc ^3.1.0`，测试用 `vitest ^3.2.4`、`@vue/test-utils ^2.4.6`、`jsdom ^26.1.0`。未引入第三方组件库，组件自建在 `web-ui/src/components/`。 |
| 服务状态存储 | SQLite（MVP） | Gateway MVP 使用 Python 标准库 `sqlite3` 保存端侧命令、执行、审核与审计状态；不用于替代 fast-agent 的运行时会话文件，也不复制 Research Mapping / LLM-Wiki 的领域正文。 |
| Research Mapping 图存储 | TerminusDB | Research Mapping 的候选与正式 TaskNode/DependencyEdge 图快照使用 TerminusDB；SQLite 治理记录保存 Proposal、审批、正式版本指针和审计索引。当前镜像同时用于本地验证，具体领域持久化实现另立 ticket。 |
| Agent 运行时 | fast-agent-mcp | Gateway 后续通过 Runtime Adapter 接入；具体版本和锁定方式由 `ai4-o806` 决定。 |
| 消息队列 | Redpanda | 任务下发、上游交接与 Agent 事件统一经 Redpanda 传递。当前使用 `sci-weave/service/redpanda/` 的单节点 Compose 做本地验证，镜像 `redpandadata/redpanda:v24.3.7`；Kafka API 对宿主机暴露 19092，容器网络内为 9092。主题、分区、消费者组、保留期与 offset 提交语义由 `ai4-te1v` 定义，不在本文件记录。生产高可用与副本配置未定。 |

## 子项目结构

只有一个部署角色的服务使用独立子项目：

```text
sci-weave/<子项目>/
├── src/
│   ├── main.py         # 子项目启动入口
│   └── <模块名>/        # 产品业务代码
├── tests/             # 自动化测试
├── pyproject.toml     # Python 项目和工具配置（Python 子项目）
├── uv.lock            # 独立子项目提交自身锁文件
├── .env             # 本地环境变量，不提交
└── .env.example     # 环境变量名称和示例值，可提交
```

同一部署单元包含多个进程角色时使用项目组，组内每个角色仍是独立子项目：

```text
sci-weave/<项目组>/
├── pyproject.toml     # uv workspace 根配置
├── uv.lock            # 组级唯一锁文件
├── .env             # 组级共享变量，不提交
├── .env.example
├── Dockerfile         # 构建与部署文件属于项目组
├── compose.yaml
├── README.md
└── <子项目>/           # 每个进程角色一个子项目
    ├── src/main.py
    ├── tests/
    ├── pyproject.toml
    ├── .env
    └── .env.example
```

- 服务和 MCP 子项目必须遵守上述 Python 结构；项目目录名表达部署角色，`src/<模块名>/` 使用简洁职责名。
- 项目组只做组织，不承载源码；`Dockerfile`、`compose.yaml` 和组级锁文件放在项目组根目录。
- 组级 `.env` 放跨角色共享变量，子项目 `.env` 放角色专属变量；两处都只提交 `.env.example`。
- 被至少两个子项目复用的代码放**归属边界**的 `shared/` 目录，由子项目以 path 依赖引用；只通过进程边界传递的契约不建共享包。
  - 同一项目组内：`sci-weave/<项目组>/shared/`，共享代码随组级锁文件解析。
  - 同一部署边界内（如 `sci-weave/centre-control/`）但分属不同独立项目时：`sci-weave/<边界>/shared/`。该 `shared/` 只是代码归属边界，不产生组级 `pyproject.toml` 或组级 `uv.lock`，各调用方各自提交锁文件。
- 跨项目组复用的代码不再设 `sci-weave/shared/` 顶层共享目录；确有跨边界复用时另立决策。
- `pyproject.toml` 是 Python 标准项目配置，不绑定管理工具；本项目统一使用 uv 读取该配置、生成锁文件、同步环境与运行项目。
- 前端 Vue 子项目使用自身的 `package.json`、锁文件、`src/` 和测试目录；真实 `.env` 同样不得提交。
- 所有路径、监听地址、端口、令牌、数据库位置和外部服务地址通过环境变量提供，不能硬编码进源码或测试。
- 新增或升级依赖前，必须先有 fer ticket，随后在子项目清单和锁文件中声明，并在对应 ticket 回写来源、用途、许可证和验证结果。

## 已确定工具

- Python 子项目统一使用 uv 管理虚拟环境、依赖同步、命令执行与锁文件；`pyproject.toml` 仍是工具无关的 Python 项目配置。
- 同一项目组的多个 Python 子项目使用 uv workspace，由组级 `pyproject.toml` 声明成员，组级提交唯一 `uv.lock`。

## 未确定项

- 生产部署、容器编排、密钥管理和 CI。
- Redpanda 的生产形态：副本数、保留期、跨机器访问的暴露方式。
- `centre-control` 内各服务是否打成一个镜像、在单容器内多进程运行，与现行“不作为同一个部署单元”规则冲突，待裁决。
