---
id: ai4-ufqu
status: in_progress
deps: []
links: [ai4-yyy9, ai4-xup8, ai4-v19u, ai4-353s]
created: 2026-10-19T01:28:09Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-kpvp
tags: [wayfinder:grilling]
---
# Task Agent 运行时与套件接入方案

## Question
确定首版 Task Agent 的运行时形态及其与 Agent 套件的接入边界。需要比较轻量的 MCP Agent 运行时与现有交互型 harness 等方案，明确运行时负责什么、平台负责什么、如何接入 MCP/Skills/Hooks、如何承载单次执行 loop、如何保存执行上下文以及如何支持人工审核和返修。该票不实现运行时，也不决定最终基础设施部署。

## Acceptance Criteria

形成可供审核协作和任务交接流程使用的 Task Agent 运行时决策：明确首选运行时或适配策略、套件接入方式、平台与运行时职责边界、单次执行 loop 的生命周期，以及人工审核/返修所需的最小上下文接口。


## Notes

**2026-10-19T01:53:57Z**

事实验证（2026-10-19）：使用 uv 将 PyPI 包 fast-agent-mcp 安装到临时目录，解析版本为 0.10.46，未修改仓库依赖或锁文件。上游 evalstate/fast-agent 文档显示该工具支持 Agent Skills、MCP Server 连接、Hooks、Human Input、A2A/ACP，并提供 use_history 配置；包内存在 history、compaction、session history 等模块。因此‘没有上下文管理’需要修正为：具备可选会话历史能力，但平台仍可关闭或不依赖其隐式历史，显式注入平台上下文。当前暂定方向：首版使用 fast-agent-mcp + TaskNode 模板；平台管理身份、授权、消息和审计，运行时装载已授权套件；Task Owner -> Task Agent 通过平台消息队列，Task Agent -> Task Owner 首版通过邮件；需要继续确认运行时的历史开关、模板边界和邮件交接协议。

**2026-10-19T02:11:59Z**

本轮讨论约束：Task Agent 输入分为两条逻辑通道。Task Owner 消息需要立即处理，并结合该 Owner 之前的消息和 Agent 处理结果；上游 TaskNode 交接消息独立处理，若存在多个上游，应先收集满足启动条件的上游消息再执行。两类消息可以复用同一队列基础设施，但触发、优先级、聚合和上下文规则必须分开。Task Agent -> Owner 暂定采用 Buffer + Codex Hook 主动发现/拉取 + 邮件仅作通知的混合方案。fast-agent-mcp 的历史机制不立即关闭或采用，先研究其历史保存、恢复、窗口、压缩及其与独立 loop/外部 Worker 的关系后再决定。

**2026-10-19T02:16:19Z**

本轮进一步收敛：上游 TaskNode 交接消息优先于 Owner 消息，因为上游消息未齐表示任务尚未满足启动条件；Task Agent 先收集所有必要上游消息，至少执行一轮后，才开放 Owner 消息通道。上游交接消息按每个上游只提供一次建模，不作为持续对话反复注入。Owner 消息在上游启动阶段暂不处理，待首轮上游驱动执行结束后进入后续处理。Task Agent 本身不维护跨 loop 的历史或双通道上下文，外围调度/Worker 程序负责消息收集、优先级、上下文拼装、历史保存和 loop 创建。fast-agent-mcp 历史机制暂不做取舍，后续单独研究。当前票据保持开放。

**2026-10-19T02:20:33Z**

已固化的暂定结论：首版选择 fast-agent-mcp + TaskNode 模板；外围 Worker/调度程序负责 loop 创建、消息收集、通道优先级、上下文拼装和历史管理；Task Agent 不自行维护跨 loop 历史。输入分为上游交接通道和 Owner 消息通道：先收集必要上游交接并至少执行一轮，再开放 Owner 消息；上游消息每个上游只提供一次，Owner 消息后续结合 Owner 消息历史与 Agent 处理结果。两类消息可共用队列基础设施但语义独立。反向通信暂定为 Buffer + Codex Hook 主动发现/拉取 + 邮件通知，邮件不承担审核状态。运行时历史机制尚未最终决定，等待独立源码验证票。

**2026-10-19T02:26:21Z**

已完成第一方源码调研并写入 docs/端侧Agent运行时调研.md：建议 fast-agent-mcp 作为外围 Worker 调用的 Task Agent 运行时，采用 Harness API；TaskNode 模板生成最小权限 Agent profile；Worker 管理上游收集、Owner 消息、上下文、审计和 Buffer；A2A 暂不作为内部消息队列；运行时 history 取舍继续由 ai4-glmy 验证。文档不引入依赖或产品代码。

**2026-10-19T02:46:39Z**

新增前沿候选：物理隔离 Task Owner 与上游 TaskNode 的触发路径。暂定方向是 Owner 的 Codex 通过 A2A 调用常驻 Task Agent Gateway，Gateway 负责授权、Owner Command 持久化、审计和按需创建/控制短生命周期 Worker；上游 TaskNode 的一次性交接继续进入消息队列和上游收集器，收齐并满足 Dependency Edge 后启动 Worker。A2A 不要求 Worker 常驻，Gateway 才常驻；Gateway 内部可用作业队列，但 Owner 的外部通信语义不变。细节由新增子票讨论。

**2026-10-19T03:03:47Z**

设计与验证更新（2026-10-19）：采用 fast-agent-mcp 的端侧运行形态已通过最小原型验证。外围程序可创建短生命周期 Python Worker，Worker 经 Harness API 启动 Task Agent loop、完成后退出；A2A 路径也可启动 fast-agent-mcp Agent。原型位于 drafts/fast-agent-startup-test/，使用项目 .venv 与 fast-agent 内置 passthrough 模型，不需要模型凭据；运行命令为 .venv/bin/python drafts/fast-agent-startup-test/run_startup_tests.py。验证结果：外部子进程回显 external process message；本地 A2A server 经 fast-agent A2A client 成功返回 A2A owner message。该结果仅证明启动路径，不证明消息队列、授权、Buffer、审计或真实模型调用。由此更新运行时边界：短生命周期 Worker 不承载长驻 Owner 通信；任务结束后释放，持久化状态保留在平台侧。

**2026-10-19T03:40:53Z**

子决策“fast-agent-mcp 历史保存、恢复与上下文隔离验证”已完成：复用每 TaskNode 固定 Harness 会话；不引入 SQLite 用于模型记忆；Gateway 控制稳定 session_id 与调用串行化。详见 docs/fast-agent-mcp上下文管理调研.md。

**2026-10-19T05:47:44Z**

Wayfinder 前沿结论（2026-10-19）：Q1-Q8 已确认，Q8 采用 A2A Human Input 交互而不是默认邮件往返。Personal Harness（Codex）是 Task Owner 控制的 A2A 客户端和审核客户端，不运行平台 Worker、不承载服务器端 Hook，也不直接管理 Task Agent 会话。Task Agent 使用 fast-agent-mcp + TaskNode 模板；平台/Gateway 负责身份授权、Owner Command、消息编排、审计、Buffer、Execution Record 和会话键，短生命周期 Worker 负责一次受控 loop。Task Owner 只能管理执行投影和提交，不得通过运行期指令修改 TaskNode 目标、依赖、激活条件或正式路线；Task Agent 只能读取正式数据并创建受控 Buffer Submission，不能直接写正式 Mapping/Wiki、审核决定或下游交接。

Q8-Q10 修正：A2A 可返回 Task Agent 最终文字回复；fast-agent A2A 已验证 INPUT_REQUIRED/后续输入恢复和取消，但默认 human_input=True 是本地 UI 回调，远程 Codex 需要 Gateway 显式桥接。Owner 指令先鉴权、持久化、幂等确认和审计；普通指令在 TaskNode 激活后执行，暂停/取消可优先生效。每个 TaskNode 至少配置一名 Owner；自动执行需要人工输入时指向该 Owner，不存在无 Owner 节点。
