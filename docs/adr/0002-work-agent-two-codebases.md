# Work Agent 运行时分两份源码，不抽共享库

Task Agent 与 Centre Agent 共用同一套架构，但源码分成两份，互不 path 依赖。中央控制面要部署上服务器，研究员套件还要带 skill、服务模板和可安装的运行时，形状不同，抽一个共享库会把两边焊死。

## Status

accepted（2026-10-22）

## Considered Options

1. **一份运行时，套件只打包**（否决）：源码放在 `centre-agents`，套件从这里打出。否决理由：套件要比中央服务多出 skill、Agent 定义样例和给研究员安装的库，不是中央服务的裁剪版。
2. **顶层共享包**（否决）：两边 path 依赖同一份代码。否决理由：跨部署边界没有共享目录；共享之后，改中央预审的启动方式会直接改到研究员机器上的库。
3. **两份源码，规格对齐**（采纳）：行为以「最小 Work Agent 实现规格」为准。状态机、Worker Lease 和处置面工具必须两边一起改。Agent 定义允许不同。

## Consequences

- Centre Agent 落在 `sci-weave/centre-control/centre-agents`。它是中央服务器上的预审服务，Agent 定义写死，同样是 `gateway/mcp`、`gateway/subscriber` 两个常驻进程再拉起 `fast-agent-mcp` 子进程。现有 `sci-weave/task-agent/` 用 `git mv` 作为它的起点，不是最终形态。
- Task Agent 的分发物落在 `sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent`。平台不在这里启动服务。三块是：教研究员改 Agent 定义的 skill、只负责启动的服务模板、运行时 libs。libs 预置 fast-agent 卡片样例。服务模板调用 libs，不把 Gateway 再写一遍。
- 研究员只能改 Agent 定义（指令、模型、允许的领域 MCP）。skill 的读者是研究员自己的 Personal Agent，不教改 Gateway。
- 研究员机器上的两个 gateway 进程用用户级自启动常驻。hooks 只在打开 harness 时检查，没跑就拉起，不掌管生命周期。关掉 harness 不得停订阅。
- 两处都落地后删除 `sci-weave/task-agent/`。迁进去的旧代码仍含 `submit_owner_command`，那是起点，不是现行契约。

## 相关

- 架构：`docs/data-flow/work-agent.md`
- 规格：`.tickets/ai4-z3z4.md`
- 套件：`.tickets/ai4-za77.md`
- 端侧归属：`.tickets/ai4-we38.md`
