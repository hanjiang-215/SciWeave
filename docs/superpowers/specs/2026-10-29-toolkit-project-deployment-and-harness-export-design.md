# Agent 套件项目级部署与 Harness 导出设计

- 日期：2026-10-29
- 状态：设计共识收敛稿，供后续实现规划与验收使用；本规格本身不改变现有安装器或运行代码
- 适用范围：`project-owner-agent-toolkit`、`researcher-agent-toolkit`、Researcher 套件内嵌的 `deploy-task-agent` 与 `suitecheck`
- 上游规格：[`2026-10-23-agent-suite-boundary-design.md`](2026-10-23-agent-suite-boundary-design.md)
- 现状依据：[`sci-weave/toolkits/README.md`](../../../sci-weave/toolkits/README.md)、两套 `suite.yaml`、Researcher Task Agent 部署说明

## 1. 问题

当前套件把几种不同生命周期的内容混在一个安装模型里：

- Skills 与 MCP 卡片实际上属于用户使用的 Harness，但安装器把它们复制到 `~/.sciweave/*`，并要求用户手工把目录接入 Harness；
- Task Agent 的代码、SQLite、会话和服务定义又属于一个可运行实例，当前默认放在用户目录，并依赖 POSIX shell 与 Linux systemd；
- `suite.yaml` 的 `install`/`check` 是可执行 shell 命令，`suitecheck run` 会直接执行它们，跨平台和跨 Harness 时没有稳定的公共契约；
- 项目目录、用户级配置、生成内容、用户自定义定义和运行态数据的所有权不清晰；
- SciencePal bridge 有 Windows `.cmd` 入口，但这不能代表整个 Researcher 套件或 Task Agent 支持 Windows。

这些问题会导致 Harness 注册配置与运行时部署互相覆盖，也会导致一个用户的多个项目错误地共用代码、数据库或服务状态。

## 2. 目标与非目标

### 2.1 目标

1. 以 Harness 的项目工作目录为项目根，建立项目级的 SciWeave 运行边界。
2. 将 Skills/MCP 接入收敛为“套件提供可发现输入，Harness 自行注册”，不再假设某一种 Harness 配置目录或格式。
3. 将运行代码、SQLite、会话、日志和服务配置绑定到一个明确的项目实例。
4. 保留用户级服务管理器，但让每个服务实例显式绑定一个项目根；首期只承诺 Linux systemd 自动托管。
5. 将 `suite.yaml` 变为声明式清单，支持跨平台只读校验和跨平台导出。
6. 为 Windows 提供逐项能力边界和人工操作建议，不把局部 `.cmd` 入口误报成完整平台支持。
7. 明确生成内容、自定义项目内容、秘密和运行态数据的 Git 生命周期。

### 2.2 非目标

- 本规格不选择或实现任何具体 Harness 的私有配置格式；
- 本规格不要求套件安装器直接修改 DSH、Cursor、WorkBuddy、Claude Code 等 Harness 的配置；
- 本规格不承诺首期在 Windows 上自动托管 Task Agent，也不把未验证的 Python runtime 标记为 Windows 已支持；
- 本规格不改变中央服务、领域 MCP、消息协议、权限能力或治理语义；
- 本规格不把用户凭据复制进 Harness 输入目录；
- 本规格不把中央 Centre Agent 重新变成一个发给用户安装的套件。

## 3. 规范性术语

- **项目根**：Harness 提供的工作目录。Harness 没有工作目录概念时，必须由用户显式指定；不得从 shell 当前目录猜测，也不得静默退回用户目录。
- **项目运行实例**：绑定一个项目根的 Task Agent 代码、配置、状态、数据和服务实例集合。
- **Harness 输入目录**：套件导出器为 Harness 生成的自包含目录，包含 Skills、MCP 卡片、套件清单和配置指导；它是 Harness 的输入，不是 Harness 私有配置目录。
- **生成目录**：由导出器完全维护、可原子刷新且不接受用户直接修改的目录。
- **项目自定义目录**：用户可以修改的 Agent 定义、Workflow 声明和本地资源目录；生成器不得覆盖其中的未知文件。
- **能力声明**：套件清单中描述角色、MCP 能力、平台支持、所需环境变量和导出内容的机器可读信息。

## 4. 目标目录模型

项目根下的默认结构为：

```text
<project-root>/
└── .sciweave/
    ├── harness/
    │   └── <suite-id>/              # 生成的 Harness 输入目录
    │       ├── suite.yaml           # 已解析/复制的声明式清单
    │       ├── manifest.json        # 稳定的机器可读导出索引
    │       ├── skills/              # 套件声明的 Skills
    │       ├── mcp/                 # 套件声明的 MCP 卡片
    │       └── configuration.md     # 不含真实值的配置指导
    ├── runtime/                     # 项目实例代码、启动入口和依赖环境
    ├── data/                        # SQLite、会话、日志、队列 offset 等运行态
    ├── project/                     # 用户自定义 Agent/Workflow/本地资源
    ├── .env                         # 可选，项目实例秘密；必须被忽略
    └── .gitignore
```

目录职责如下：

- `harness/<suite-id>/` 是生成目录。Harness 获得该目录路径后自行发现、注册或报告不支持项；套件导出器不写 Harness 私有配置。
- `runtime/` 与 `data/` 默认属于项目运行实例。每个项目拥有独立的 SQLite、会话、日志和 Worker 状态，不得默认复用另一个项目的状态库。
- `project/` 是用户自定义输入。用户可以修改其中的定义和资源；升级或重新导出不得覆盖它。
- `.env` 可以承载项目实例运行所需的秘密，但不得进入导出目录、日志、清单或 Git。实现应优先支持外部环境注入；项目 `.env` 是受控的兼容方式，不是跨项目复制凭据的机制。

`.sciweave/` 的默认忽略策略必须分类表达：运行态、生成代码和秘密默认忽略；允许明确放行非秘密的项目定义或清单模板。不能用一个裸 `*` 使所有项目定义永远无法共享。

## 5. Harness 接入契约

### 5.1 套件负责的内容

套件必须提供：

- 可解析的声明式套件清单；
- 清单声明的 Skills 与 MCP 卡片；
- 每个输入项的相对路径、名称、版本和能力信息；
- 所需环境变量名称、用途、必填条件和配置步骤；
- 平台支持矩阵与未验证能力的明确标记；
- 不依赖真实凭据的自包含 Harness 输入目录。

### 5.2 Harness 负责的内容

Harness 必须自行决定：

- 如何把 Skills 映射到自己的项目级或用户级 Skill 配置；
- 如何把 MCP 卡片映射到自己的注册格式；
- 是否支持项目级配置；
- 是否支持自动导入、确认执行、Hook 或服务启动；
- 不支持某项时，向用户报告缺失能力和可执行的人工操作建议。

套件导出器不得直接写入 `.dsh`、`.cursor`、Harness 私有 JSON/YAML、全局 MCP 注册表或用户级 Skill 目录。即使某个 Harness 恰好使用这些目录，也只能由该 Harness 自己读取导出目录后完成注册。

### 5.3 输出稳定性

导出同一 `suite-id` 时：

- 目标路径稳定为 `.sciweave/harness/<suite-id>/`；
- 导出内容必须自包含，不依赖原始 zip、源码 checkout 或绝对路径；
- 生成目录由导出器原子刷新；
- 生成器不得覆盖 `.sciweave/project/`、`.env`、`data/` 或生成目录之外的未知文件；
- 生成器不得读取、复制或打印令牌、密码、`.env` 值或其他本机秘密；
- MCP 卡片只能描述服务名、端点环境变量名、能力和工具，不得包含真实端点凭据；
- `configuration.md` 只列出变量名、用途、必填条件、来源和验证步骤，不填真实值。

## 6. 声明式套件清单

`suite.yaml` 继续作为套件入口，但其 install/check 字段不再是跨平台执行契约。清单应声明至少以下信息：

- `suite`、`version`、`role`、`actor`、`summary`；
- 能修改和必须禁止修改的边界；
- Skills、MCP、hooks、cron 和运行时载荷的相对路径；
- MCP 能力上限和工具白名单；
- 所需环境变量及其用途，不含变量值；
- 支持的平台、平台状态（`supported`、`manual`、`unsupported`、`unverified`）和限制说明；
- Harness 输入目录的导出规则；
- 运行实例需要的代码、数据和服务角色；
- 配置指导文档的路径和版本。

实现阶段应提供跨平台 Python 导出器，作为复制、路径处理、清单解析、秘密排除和只读校验的唯一公共实现。POSIX shell、PowerShell 或 CMD 可以作为薄入口，但不得分别重写核心导出逻辑。

`suitecheck check` 只读验证：它检查清单闭合性、引用存在性、能力上限、平台声明、秘密边界、输出路径规则和配置指导完整性。`suitecheck run install/check` 不再执行清单里的任意 shell 命令；未知命令不得因为出现在清单中就被执行。

## 7. 项目服务与生命周期

### 7.1 服务绑定

Task Agent 仍可以由用户级服务管理器托管，但每个项目必须拥有独立服务实例：

- 服务名或实例标识必须包含稳定的项目标识；
- 服务配置必须显式记录项目根、runtime 路径、data 路径和环境文件位置；
- 启动前必须校验项目根和关键路径仍然存在；
- 一个项目的服务不得静默读取另一个项目的 SQLite 或代码；
- 项目根无法由 Harness 工作目录可靠确定时，安装必须停止并要求用户指定。

首期自动托管平台为 Linux `systemd --user`。其他平台可以获得人工操作建议，但不应被报告为具有等价的自动重启、日志和生命周期保证。

### 7.2 项目移动

项目目录移动后，服务实例必须检测原绑定路径失效并报告“需要重绑”。不得根据模糊的目录名或当前工作目录自动改指向新路径。重绑操作必须由用户明确发起，并重新写入服务实例的项目根和路径配置。

### 7.3 升级

升级或重新导出必须：

- 只替换对应版本的 runtime 和 Harness 生成内容；
- 保留项目定义、Workflow、本地资源、`.env`、SQLite、会话和日志；
- 在替换前完成清单和路径校验；
- 失败时保留旧的可运行版本或提供明确恢复路径；
- 不因升级覆盖用户自定义文件。

### 7.4 卸载

默认卸载只移除服务注册、运行代码和 Harness 生成目录，并保留 `data/`、`project/` 和 `.env`。删除运行数据必须是独立、明确且可确认的操作，不得作为普通卸载的隐式副作用。

### 7.5 旧安装迁移

现有 `~/.sciweave/task-agent` 安装保留兼容迁移路径，但不再作为新项目安装的默认目标。迁移工具必须：

- 识别旧安装和其项目绑定状态；
- 展示将迁移的代码、状态、服务和配置；
- 要求用户明确选择目标项目根；
- 支持迁移后重绑 systemd 实例；
- 不删除旧数据，除非用户单独确认；
- 无法可靠判断旧安装归属时停止并报告，而不是猜测。

## 8. Windows 支持边界

Windows 支持按能力逐项声明，不以“存在 `.cmd` 文件”作为端到端支持证明。

首期规则：

- SciencePal bridge 的 `.cmd` CLI 可以单独声明为 Windows 可用，但必须有独立的命令、退出码和路径测试；
- Project Owner/Researcher 的 Harness 输入导出可以在 Windows 上声明为 `supported`，前提是 Python 导出器和路径处理经过 Windows 验证；
- Researcher Task Agent 的完整安装、后台服务、自动重启和 harness hook 在未完成 Windows 验证前必须标记为 `manual`、`unsupported` 或 `unverified`，不能显示为安装成功；
- Windows 的 PowerShell/CMD 操作脚本或命令可以提供人工执行建议；Harness 有明确的用户确认与执行能力时可按其安全策略执行，否则只能展示给用户；
- Agent 不得在没有用户确认或 Harness 授权的情况下执行复制代码、写入 `.env`、注册服务、启动服务、停止服务等副作用操作；
- Windows 文档必须区分“已验证步骤”“未验证步骤”和“暂不支持步骤”，并给出用户可以自行执行的替代路径。

## 9. 安全与权限

- 套件清单、Skills、MCP 卡片、manifest 和配置指导不得含真实凭据；
- 导出器不得扫描并回显 `.env` 值；错误消息不得包含 token；
- `.sciweave/.env`、SQLite、会话、日志、runtime 生成环境和服务注册文件必须默认进入忽略规则；
- 项目共享内容只能是非秘密的 Agent 定义、Workflow、资源声明和配置模板；
- Harness 注册不改变中央 MCP 的 Bearer 鉴权和服务端能力校验；
- 套件声明的能力上限不得超过 `actor` 的权限上限；
- 生成目录与项目自定义目录必须有可验证的覆盖边界，升级不能借由未知文件路径覆盖项目内容。

## 10. 验收场景

### 10.1 Harness 与项目定位

1. Harness 提供项目工作目录时，导出器把目标绑定到该目录下的 `.sciweave/`。
2. Harness 不提供工作目录且用户未指定目录时，导出器停止并说明需要项目目录。
3. 导出器不能通过当前 shell 目录或用户目录静默选择目标。
4. 导出后 Harness 获得唯一的 Harness 输入目录路径，并可根据清单列出 Skills、MCP 和配置要求。
5. 一个不支持项目级 MCP 注册的 Harness 能得到明确的人工注册建议，且套件没有改写其全局配置。

### 10.2 生成与自定义边界

1. 首次导出生成完整、自包含的 `.sciweave/harness/<suite-id>/`。
2. 重复导出原子刷新生成内容，保留 `.sciweave/project/`、`.env` 和 `data/`。
3. 生成器拒绝覆盖生成目录之外的未知文件。
4. 清单、卡片和配置指导中不存在真实 token、密码或 `.env` 值。
5. `.gitignore` 忽略运行态和秘密，同时允许明确放行的非秘密项目定义。

### 10.3 服务与生命周期

1. 两个项目各自导出并启动时，服务、SQLite、会话和日志完全隔离。
2. 项目目录移动后，旧服务实例拒绝启动并报告需要显式重绑。
3. 升级不覆盖项目定义、数据或凭据。
4. 普通卸载保留数据；数据删除必须单独确认。
5. 旧的 `~/.sciweave/task-agent` 安装能被识别，并得到迁移/重绑指引。

### 10.4 平台

1. Linux systemd 路径验证项目级独立服务实例、重启和日志行为。
2. Windows 验证 Python 导出器、路径含空格、清单解析和无凭据输出。
3. Windows 验证 SciencePal `.cmd` 的成功退出码、失败退出码和路径含空格。
4. 未验证的 Windows Task Agent 后台服务不会被报告为成功安装。
5. Windows Harness 无副作用执行能力时，套件只输出人工操作指引，不自动执行命令。

## 11. 实现拆分建议

后续实现应按可独立验证的垂直切片拆分：

1. 声明式清单与平台状态模型；
2. Python 导出器及生成目录原子刷新；
3. `.sciweave/` 项目布局与分类 `.gitignore`；
4. Harness 输入目录和 `.env` 配置指导；
5. Linux 项目绑定 systemd 服务实例；
6. 旧 `~/.sciweave/task-agent` 迁移与显式重绑；
7. suitecheck 只读验证与 Windows 路径测试；
8. Windows 人工操作建议和 SciencePal `.cmd` 验证；
9. 两套现有套件清单、README、Skills 中的旧安装语义迁移。

每个切片都必须保留真实平台边界：代码实现、文档声称和测试结果三者不一致时，以最小已验证能力为准。

## 12. 当前未决实现问题

这些问题不影响本规格的目标和边界，但实现前必须形成独立工单或 ADR：

- 稳定项目标识如何生成，以及项目重命名是否保持同一服务实例；
- Linux systemd 实例名的转义规则和项目路径含空格时的 unit 写法；
- Windows “人工操作建议”输出为 PowerShell、CMD 还是两者；
- Python 导出器放在 `suitecheck` 子项目、独立工具包还是套件共享入口；
- manifest.json 的版本和精确 schema；
- 生成目录原子替换在 Windows 文件锁存在时的恢复策略；
- 外部环境注入与项目 `.env` 的优先级和冲突报告方式；
- 旧安装中无法归属项目的 Worker 状态如何由用户选择迁移或只读保留。
