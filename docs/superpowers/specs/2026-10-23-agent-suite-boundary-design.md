# Agent 套件接入与协作边界设计

- 日期：2026-10-23
- 关联工单：[`ai4-v19u`](../../../.tickets/ai4-v19u.md)（地图分支，由 `ai4-ufqu` 关闭时迁移至此）
- 状态：边界规格收敛稿，供后续实现规划使用；不引入运行时依赖，不做实现选型
- 主要输入：`docs/端侧Agent运行时调研.md`；[「Agent 以消息驱动，Gateway 的 MCP 只负责返修」决议](../../../.tickets/ai4-dhpv.md)（两类 MCP 分工）；[「Task Owner 通道与上游交接队列物理隔离」决议](../../../.tickets/ai4-353s.md)（Owner 通道 MCP）；[「Work Agent 统一架构」](../../data-flow/work-agent.md)；`docs/data-flow/centre-agent.md` 的「需要的套件」段

## 目的

厘清 Agent 套件三件套——MCP、Skills、Hooks/extensions——在 SciWeave 中的职责、接入方式和协作边界，收敛成可供后续规划使用的规格。本文件回答「平台提供什么、用户自带什么、两者在哪里衔接」，不选择具体 MCP SDK、Skills 格式或 hook 引擎。

## 边界一：两类 MCP，面向对象不同

继承 `ai4-dhpv` 的决议，全平台 MCP 分两类，职责不混用：

| 类别 | 使用者 | 作用 | 例子 |
| --- | --- | --- | --- |
| **Agent Gateway 的 MCP**（task-agent、centre-agent 各自的处置面） | 人（Owner / Project Owner）经自己的 harness | 返修、处置、回答提问、观察 | `query_execution`、`review_execution`、`answer_question`、`cancel_execution`、`health` |
| **平台领域 MCP**（Mapping、Wiki、草稿箱） | Agent（端侧 Work Agent）与后续接入方 | Agent 干活的工具：读正式数据、读写草稿、提交 candidate | `centre-control/research-map`、`research-wiki`、`buffer` 的工具 |

约束规则：

- 「MCP 只做返修」只约束第一类。第二类是 Agent 的能力来源，不受此限。
- 领域 MCP 不得包含「代替人批准」「启动或调度 Worker」「直接写正式图」「一次调用同时改两个领域」的工具（沿用 `centre-agent.md` 的套件排除清单）。
- 任何 MCP 都不打开新的入站可达面：端侧订阅器只主动出站连接中央队列，领域 MCP 只接受 Agent 的受控调用。

## 边界二：运行时与 Worker 的套件装载边界

按 `docs/端侧Agent运行时调研.md`，Work Agent 的一次 loop 由短生命周期 Worker 承担，`fast-agent-mcp` 是受外围 Worker 调用的运行时，不是调度器或消息队列。套件装载遵循：

- **最小权限 Agent profile 生成**：每个 TaskNode 模板只装载该任务需要的 MCP server 与显式工具白名单。默认不连接任意 MCP、不启用不限定的工具过滤。示例见调研文档的 TaskNode Agent Profile 轮廓。
- **Skills 只认显式清单**：运行时不得从默认技能目录自动发现 `SKILL.md`（自动发现会被授予 shell access）。每个 TaskNode 模板显式声明可信 Skill 清单；无必要时不启用 Skills 与 shell。
- **Hooks 只用于 Worker 进程内受控行为**：启动前校验、提交前校验、执行后记录。Task Owner 的个人 Codex Hook 绝不能作为服务器端/Worker 端 Agent Hook。
- **平台装配上下文，运行时只执行 loop**：消息收集、Dependency Edge 激活判断、上下文拼装、运行超时、审计和执行记录回写全部由外围 Worker 在调用前/后完成；运行时内部 session 历史是可选执行轨迹，不是平台权威事实。

## 边界三：平台提供能力与用户自带能力的分工

| 能力 | 归属 | 依据 |
| --- | --- | --- |
| 端侧 Work Agent 部署套件（gateway/mcp、gateway/subscriber、worker 的源码与运行配置） | 平台提供，发给研究员 | `deploy-task-agent` 与 `centre-agents` 两份源码，见 ADR-0002 |
| 平台领域 MCP（Mapping / Wiki / 草稿箱） | 平台提供 | 中央各子项目的 MCP 工具 |
| 中央队列订阅与消息载荷语义 | 平台提供（语义归属 `ai4-te1v`） | Redpanda 已选型 |
| 预审判据、冲突矩阵、混合候选生成等 Centre Agent 技能 | 平台提供，Git 版本化 | `centre-agent.md`「需要的套件」 |
| Task Owner 的个人 harness（Codex CLI / Cursor / Claude Code） | 用户自带 | 只作为 MCP 客户端注册网关地址与令牌 |
| Owner 侧额外的个人信息、模型凭据、私有 Skills | 用户自带 | 平台不读取、不复制、不托管这些内容 |

判定原则：**能让多个用户或两个以上 Work Agent 复用的能力进平台套件；只属于单个研究员本机的配置与凭据留在用户侧。** 平台套件只提交 `.env.example`、模板和代码，不打包真实凭据、个人知识或认证令牌。

## 边界四：与消息协作及治理流程的接口边界

- **任务下发只走消息队列，不经 MCP。** 根任务首条消息由 Project Owner 发布；上游交接由领域正式版本发布触发。MCP 处置面不创建新执行（无 `submit_owner_command`），`review_execution` 无 `accept`；「把草稿转候选」发生在研究员的 Codex 与领域 MCP 之间，不在 Gateway。
- **订阅是出站连接。** 端侧订阅器长期持有 consumer group 与 offset；订阅器与 MCP 进程分离，任何一侧重启不牵连另一侧。
- **Skill / Hook 的接入以 Worker 为界。** 平台技能作为目录或模板随套件分发，由 Worker 在 loop 装载时引用；Hooks 不跨进程、不作为中央服务的能力扩展点。
- **留痕与治理不受套件影响。** 接口层调用账本与领域治理记录由中央各服务自行记录；套件接入不绕过审计，也不在 Agent 侧再造审计副本。

## 范围外（本票不决策、不实现）

- Agent Kit manifest、目录结构、权限声明、版本兼容与配置覆盖规则：已由 `ai4-jfvy` 明确转后续独立阶段。
- Skills/Hooks 模板体系和多套件定制市场。
- ZIP 打包与跨服务器安装部署。
- 具体 MCP SDK、Skills 格式、hook 引擎、模型与凭据选型。

## 后续落地建议

1. `ai4-kpvp`（端侧 Agent 协作与治理）与 `ai4-te1v`（消息队列语义）负责人可依据本文件校准各自分支里的「套件接入」子项。
2. 实现阶段把种子 Stage 定为：领域 MCP 工具白名单模板 + TaskNode 最小权限 profile 生成器 + Worker 显式 Skills 装载清单，三者随首个 Work Agent 闭环（`ai4-z3z4`）落地。
3. 研究者邮箱通知、A2A 对外暴露等「后续可选项」不在本阶段创建工单，待闭环稳定后另行发起。