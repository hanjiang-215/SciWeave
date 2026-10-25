---
id: ai4-cdia
status: closed
deps: []
links: [ai4-za77, ai4-8aa0, ai4-o2n3]
created: 2026-10-23T02:18:54Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-z3z4
tags: [toolkit, task-agent, multi-agent, fast-agent, skills, spec, ready-for-agent]
---
# 研究员 Task Agent 技能组与多 Agent 资源边界

为研究员端侧 Task Agent 建立一个名为 deploy-task-agent-skills 的技能组，并收敛技能、Agent 定义、Agent 资源库、MCP 资源库与 fast-agent 多 Agent 工作流的可交付边界。

技能组支持 Router、Orchestrator、Parallel、Agents as Tools 四类内部工作流；平台提供标准资源，研究员可在 local-agent-libs 与 local-mcp-libs 增加自定义资源。多 Agent 仍运行在一个 Work Agent Worker 内，共享一个平台级 ExecutionRecord，最终由最终写入 Agent 产生一个 draft_id。

本票只做规格和资源组织决策，不实现多 Worker 分布式编排。

## Design

### 技能组目录

技能组目录固定为 `deploy-task-agent-skills`，拆分为五个短技能，每个技能只有自己的 `references/`：

- `create-agent`：复制并填写 Agent 定义。
- `compose-workflow`：组合 Router、Orchestrator、Parallel 和 Agents as Tools 四类工作流。
- `configure-mcp`：选择标准或本地 MCP 资源并配置环境变量。
- `verify-task-agent`：用假上游消息和假草稿箱验证完整链路。
- `troubleshoot`：按边界定位配置、服务和工作流故障。

### 目录职责边界

| 目录 | 职责 |
| --- | --- |
| `agent-definitions/` | 可复制的 Agent 定义、schema；不包含执行逻辑 |
| `libs/agent-libs/` | 纯 YAML/JSON Agent 行为资源（prompt、validator、formatter 等），由 runtime 加载 |
| `libs/mcp-libs/` | 纯 JSON MCP 服务卡片/工具目录，由 runtime 加载 |
| `libs/workflow-libs/` | 纯 YAML Workflow 协议、schema 和四类工作流示例 |
| `libs/local-agent-libs/`、`libs/local-mcp-libs/` | 研究员自定义资源，只扩展或兼容覆盖标准资源 |
| `custom-mcp/` | 需要 Python 实现的自定义 MCP 服务，每个服务是独立 uv 子项目 |
| `runtime/` | 状态记录、Worker Lease、配置模型、资源注册表、单 Worker 多 Agent 工作流执行 |
| `service-template/` | `gateway/mcp`、`gateway/subscriber`、`worker` 三个启动壳 |

### 多 Agent 工作流边界

- 一个平台级 Work Agent 对应一个 Worker、一个 ExecutionRecord 和一个最终 draft_id；多个内部 Agent 通过 fast-agent 工作流协作（`runtime/src/work_agent_runtime/workflows.py`）。
- `WorkflowExecutor` 是刻意的最小接缝：只有 Agent 可调用对象和草稿箱可调用对象两个协作方；它不为子 Agent 创建平台记录、租约、队列消费者或草稿。
- 工作流 `type` 必须是 Router、Orchestrator、Parallel 或 Agents as Tools；`entry_agent`、`sub_agents`、`summarizer`、`final_writer` 必须引用已声明 Agent；`final_writer` 是唯一允许最终写入的角色；`tools` 可声明 Agents as Tools 子 Agent，引用图不能成环。
- 子 Agent 不单独取得消息队列消费者组、Worker Lease 或平台级 ExecutionRecord。

### 资源加载与覆盖规则

- 平台标准资源在 `libs/agent-libs/`，研究员自定义资源在 `libs/local-agent-libs/`（或 `LOCAL_AGENT_LIBS` 指向的外部目录）。
- `ResourceRegistry` 以 `(name, version)` 唯一键登记；本地资源只允许覆盖同名的标准资源，冲突时抛 `resource_conflict`；解析时按 source 优先级（local 优先）与版本约束选最高匹配。
- MCP 服务卡片在 `libs/local-mcp-libs/`，只注册服务能力和连接方式，不实现服务；`transport` 支持 `stdio`（仅允许 `uv` 启动，项目目录经 `project_dir_env`）和 `streamable-http`（地址经 `endpoint.url_env`）；真实令牌只能经环境变量提供。

### 技能约束与权限边界

- 技能文本约束不是服务端权限边界。README 明确 Personal Agent 只能修改 Agent 定义、工作流声明和资源配置；不得修改 `runtime/`、Worker Lease、Gateway 或服务模板。
- 打开 harness 只能执行 `hooks/check-services.sh` 的用户服务检查；关闭 harness 不停止用户级常驻服务。

## 当前边界

一个平台级 Work Agent 对应一个 Worker、一个 ExecutionRecord 和一个最终 draft_id；多个内部 Agent 通过 fast-agent 工作流协作。子 Agent 不单独取得消息队列消费者组、Worker Lease 或平台级 ExecutionRecord。

## Acceptance Criteria

- [x] 技能组目录固定为 deploy-task-agent-skills，并拆分为多个短技能；每个技能有独立 references/ 长文档。
- [x] 明确 create、compose workflow、configure MCP、validate、troubleshoot 等技能的职责和触发条件。
- [x] 明确 agent-definitions、agent-libs、mcp-libs、runtime、service-template 的职责边界。
- [x] 定义 Router、Orchestrator、Parallel、Agents as Tools 的最小配置模型和组合限制。
- [x] 明确平台标准资源与 local-agent-libs、local-mcp-libs 自定义资源的加载和覆盖规则。
- [x] 明确技能文本约束不是服务端权限边界，并定义 MCP 调用与最终草稿写入的行为约定。
- [x] 明确单 Worker、单 ExecutionRecord、单最终 draft_id 的多 Agent 运行边界。
- [x] 形成可交给后续实现票的目录结构、schema、示例和验证场景。

## Notes

**2026-10-25 规格收敛（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

对照现有套件实现（`sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/`）收敛正文：五个技能及各自 references/ 已在 `deploy-task-agent-skills/` 落地；目录职责边界与 README 一致；四类工作流与 `final_writer` 唯一写约束在 `runtime/workflows.py`、`workflow-libs/README.md` 落地；本地覆盖与冲突规则在 `runtime/resources.py`（`ResourceRegistry`）落地；MCP 卡片注册协议在 `local-mcp-libs/README.md` 落地。技能约束非权限边界由套件 README「Personal Agent 不得修改 runtime/...」确认。验收八项全部勾选，置 closed。

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。
