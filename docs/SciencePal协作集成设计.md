# SciencePal 协作集成设计

> 状态：方案（2026-10-27），面向 2026-10-31 提交窗口。
> 关联：`ai4-v869`（SciencePal 执行面与中央 MCP 对接预案）、`ai4-aaff`（演示场景与证据）、`ai4-v19u`（套件边界）。
> 本文只定集成边界与落地顺序，不替代实现票；实现前按 `docs/agents/issue-tracker.md` 拆票。

## 1. 结论

**把 SciencePal 作为「科研执行面」套件接入现有 Work Agent，不要反过来把协作与治理搬进 SciencePal。**

- 协作者 = 现有 Task Agent 实例（一角色一实例），加载 `sciencepal-research` 套件。
- 套件 = 1 个 Skill（决策协议）+ 1 个 MCP bridge（确定性执行能力）+ 1 份 MCP 工具卡 + N 份协作者 Agent 定义 + 启动检查 hook。
- 地图 → 协作者：沿用现有 `task_handoff_ready` 与 `TaskNode.executor_refs`，不新增下发通道。
- 协作者 → SciencePal：bridge 通过官方 SDK 上传输入、发起 run、轮询状态、下载产物。
- 协作者 → 地图：执行报告写入中央草稿箱，人工一审后由人提交候选，Project Owner 正式化。
- 全程不要求中央 MCP 公网可达，不把 `formalize` / `candidate_review` 交给 SciencePal。

**为什么不是「纯 Skill」**：SciencePal 的操作包含令牌、文件上传、分钟级轮询、二进制产物、幂等与审计。这些靠提示词加 curl 不可靠，必须落成代码；Skill 只负责“什么时候用、怎么组织任务、怎么验收”。

**为什么不是「SciencePal 托管协作者」作为主方案**：可行，但需要公网 MCP、令牌分发和候选权限边界，4 天内风险高于收益。作为赛后增强，见 §11。

## 2. 已确认的 SciencePal 能力（2026-10-27）

从官方集成页的 Skills 包与 SDK 实测面确认：

| 能力 | 事实 | 对本项目的意义 |
| --- | --- | --- |
| Skills 包 | `GET https://sciencepal.ai/api/skills/sciencepal/download`，zip 内含 `SKILL.md`、`scripts/`、`whl/`、`.env` | 官方推荐形态就是“把操作脚本交给 Agent”；可直接作为 bridge 的参考实现 |
| SDK | `sciencepal-sdk==0.1.1`，Apache-2.0，Python ≥3.11，依赖 `httpx`、`pydantic` | 可 pin 版本进套件；许可证允许再分发 |
| 端点 | `https://sciencepal.ai/api`，Bearer `SCIENCEPAL_ACCESS_TOKEN` | 令牌来自 SciencePal 控制台，只放环境变量 |
| 发起运行 | `runs.initiate(prompt, files, agent_id, agent_select_type, web_search_on, model_name, dataset_ids, ...)` 返回 `thread_id` + `agent_run_id` | 支持文件上传、指定领域 Agent、开关联网 |
| 查询/停止 | `runs.get`、`runs.stop`、`runs.list_thread_runs`、`runs.stream`（SSE） | 无 webhook，只能轮询或 SSE |
| 沙箱 | `sandbox.get_thread_sandbox(thread_id)`、`list_files`、`read_file`、`write_file`、`download_file` | 输入上传与产物回传闭环成立 |
| Agent 管理 | `agents.create/update/list` 支持 `system_prompt`、`configured_mcps`、`custom_mcps` | 平台侧支持自定义 MCP，说明 v869 的路径 A 存在；但 `custom_mcps` 字段形状未验证 |
| 内置领域 Agent | general、biology、material、protein、plasma、patent | 协作者可按学科绑定 `agent_id`，也可 `agent_select_type=auto` |
| 终态 | `completed`、`failed`、`stopped` | 映射到 ExecutionRecord 的终态；超时需 bridge 自己判 |

**关键缺口**：`runs.get` 只返回状态与错误，不返回最终回答；最终报告在沙箱产物里，或用 SSE 读。因此任务包必须显式约定产物文件名与目录，bridge 以“下载到的产物”为准，不以模型口述为准。

## 3. 三个平面

```text
┌──────────────────────────────────────────────────────┐
│ 治理面 SciWeave（唯一事实源）                          │
│ research-map / draft-buffer / coordinator / registry  │
│ 正式图、候选、草稿、ExecutionRecord、调用账本            │
└───────────────────────┬──────────────────────────────┘
                        │ task_handoff_ready
                        │ node + trigger_revision_id + 验收条件
┌───────────────────────▼──────────────────────────────┐
│ 协作面 协作者（Work Agent，一角色一实例）                │
│ 拆任务 / 组任务包 / 调 SciencePal / 验收 / 写报告        │
└───────────────────────┬──────────────────────────────┘
                        │ sciencepal-bridge（本地 MCP，stdio）
┌───────────────────────▼──────────────────────────────┐
│ 执行面 SciencePal（领域 Agent + Sandbox）               │
│ 规划 / 代码 / 计算 / 图表 / 报告                        │
└──────────────────────────────────────────────────────┘
```

四条边界：

1. 地图不把“运行中”写进版本对象；进度是投影。
2. 协作者不直接写正式图；只写草稿与建议变更集。
3. SciencePal 不持有治理权；只产出可核验证据。
4. 每个结论可回溯到 `formal_revision_id + run_id + artifact sha256`。

## 4. 套件落位

放在研究员套件内，跟随现有 `deploy-task-agent` 一起分发：

```text
sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/
├── deploy-task-agent-skills/
│   └── sciencepal-research/
│       ├── SKILL.md
│       └── references/
│           ├── task-packet.md
│           ├── evidence.md
│           └── failure-matrix.md
├── custom-mcp/
│   └── sciencepal-bridge/                # 独立 uv 子项目
│       ├── pyproject.toml
│       ├── src/sciencepal_bridge/
│       │   ├── main.py                   # stdio MCP server
│       │   ├── client.py                 # SDK 封装
│       │   ├── store.py                  # run ledger + 幂等
│       │   └── config.py
│       └── tests/
├── libs/mcp-libs/sciencepal/mcp.json     # runtime 工具卡
├── agent-definitions/agents/
│   ├── data-collaborator.yaml
│   ├── biology-collaborator.yaml
│   └── materials-collaborator.yaml
├── hooks/check-sciencepal-env.sh
└── .env.example                          # 增 SCIENCEPAL_* 变量
```

四个接入点：

| 接入点 | 作用 | 不做什么 |
| --- | --- | --- |
| Skill | 何时委派、任务包结构、验收与失败处置、报告写法 | 不执行 SDK、不碰令牌 |
| MCP bridge | 上传、发起、轮询、下载、取消、幂等、留痕 | 不判断科研对错、不写地图 |
| MCP 工具卡 | 让 runtime 的 `allowed_mcp_resources` 能引用并展示工具 | 不承载实现 |
| Agent 定义 | 角色 instruction、允许的 MCP、默认学科/Agent | 不改 runtime 状态机 |

新增环境变量（只提交名称）：

```text
SCIENCEPAL_ACCESS_TOKEN=
SCIENCEPAL_BASE_URL=https://sciencepal.ai/api
SCIENCEPAL_RUN_DB=            # bridge 本地 run ledger，缺省放 WORKER_HOME
SCIENCEPAL_WORKSPACE=         # 允许上传/下载的根目录
SCIENCEPAL_MAX_UPLOAD_MB=25
SCIENCEPAL_DEFAULT_AGENT_ID=
```

### 4.1 运行时现状与改动点

读现有代码后的硬事实：`runtime/src/work_agent_runtime/fast_agent_runtime.py` 目前每次执行只创建一个裸 fast-agent agent——静态 instruction、`use_history=True`、**没有 `servers`、没有加载 Agent 定义、没有 Skill**；`worker_shell.py` 只把 `result_summary` 写成 `{result_summary: ...}` 的草稿。也就是说，套件装进去，协作者现在也“看不见”这些工具。

因此要真正让协作者用上 SciencePal，需要四处改动（都集中在研究员套件内，不动中央服务）：

| 改动 | 位置 | 内容 |
| --- | --- | --- |
| 加载 Agent 定义 | `fast_agent_runtime.py` | 按 `executor_refs` / 任务类型选 `agent-definitions/agents/*.yaml`，取出 instruction、allowed MCP、模型 |
| 挂 MCP servers | `FastAgentSettings` + `@fast.agent(servers=[...])` | 从 MCP catalog 生成 `mcp.servers`（stdio bridge + streamable-http 的 map/draft），只挂 `allowed_mcp_resources` 白名单内的 |
| 注入 Skill | 同上 | 把 `sciencepal-research/SKILL.md` 正文拼进 instruction（在角色 instruction 之后），保证“何时委派、怎么验收”进入模型上下文 |
| 结构化报告 | `worker_shell.py` + `draft_writer.py` | 让 agent 返回 JSON ExecutionReport；runtime 校验后作为草稿 payload 写入，而不是只写 `result_summary` |

约束与降险：

- 用 `SCIWEAVE_SCIENCEPAL_KIT=1` 开关，默认关闭，保证现有演示链路不回归；单测用假 MCP / 假 SDK。
- fast-agent 0.10.47 的 `AgentConfig.servers: list[str]` 已确认存在，可直接传 server 名。
- stdio bridge 每个 worker 启动一次，启动成本需实测；若超过 2s，改为常驻 bridge 由本地 HTTP 暴露。
- 若运行时改造在 10/30 前未稳定，兜底是 `conductor` 脚本（确定性编排，直接调 SDK + 地图 MCP）跑同一套治理链路；此时演示材料必须写“编排脚本”，不能写成“协作者 Agent 自主使用 Skill”。

## 5. bridge 工具契约

只暴露四个工具，保持“可测试、可重放、可审计”：

### 5.1 `sciencepal_start`

```json
{
  "execution_id": "exec-...",
  "instruction": "给 SciencePal 的完整任务指令",
  "agent": {"id": "agent-...", "select": "manual", "discipline": "general"},
  "files": [{"name": "iris_data.csv", "path": "/abs/workspace/iris_data.csv"}],
  "web_search": true,
  "model": null,
  "idempotency_key": "sciencepal:exec-..."
}
```

返回：`{"run_id","thread_id","status":"queued","reused":false}`。

- `idempotency_key` 落 SQLite；重复调用返回首次 `run_id`，不重复烧配额。
- 文件必须在 `SCIENCEPAL_WORKSPACE` 下，单文件与总量有上限；上传前计算 sha256 并回显。
- `select=manual` + 显式 `agent_id` 优先，保证可复现；`auto` 仅作兜底。

### 5.2 `sciencepal_status`

入参 `run_id`（或 `execution_id`）。返回 `status`、`started_at`、`completed_at`、`elapsed_s`、`error`、`last_event`。只做一次 GET，不阻塞。

状态映射：

| SciencePal | ExecutionRecord | 说明 |
| --- | --- | --- |
| `queued` / `running` | `running` | 可继续轮询 |
| `completed` | 待 `collect` 后 `completed` | 未收产物不算完成 |
| `failed` | `failed` | 记录 `error` 摘要 |
| `stopped` | `cancelled` | 人工或超时停止 |
| 本地超时 | `failed`（`sciencepal_run_timeout`） | 不自动无限重试 |

### 5.3 `sciencepal_collect`

入参 `run_id`、可选 `files`（白名单）与 `output_dir`。返回：

```json
{
  "run_id": "...",
  "thread_id": "...",
  "artifacts": [
    {"name": "result.json", "path": "runs/<run_id>/result.json",
     "size": 680, "sha256": "...", "kind": "data"}
  ],
  "manifest_path": "runs/<run_id>/manifest.json"
}
```

- 仅 `completed` 可收；递归列目录，过滤系统目录，保留相对路径。
- 二进制安全写入；落盘后重算 sha256；与任务包声明的期望产物比对，缺件返回 `sciencepal_no_artifacts` / `sciencepal_artifact_missing`。
- 不自动删除沙箱；敏感数据由协作者显式清理。

### 5.4 `sciencepal_cancel`

入参 `run_id`；幂等。已终态返回 `accepted:false`，不是错误。

错误码（稳定、可展示、不含令牌/堆栈/路径）：

```text
sciencepal_token_missing
sciencepal_unauthorized
sciencepal_unavailable
sciencepal_run_not_found
sciencepal_run_timeout
sciencepal_run_failed
sciencepal_no_artifacts
sciencepal_artifact_missing
sciencepal_artifact_hash_mismatch
sciencepal_workspace_violation
sciencepal_idempotency_conflict
```

## 6. 任务包（TaskPacket）

协作者从地图取**固定 revision** 的节点切片，不读“最新图”：

```json
{
  "schema_version": 1,
  "map": {
    "mapping_domain_id": "iris-demo",
    "formal_revision_id": "rev-7",
    "task_node": {"logical_id": "task:t1", "version_id": "t1-v1"},
    "acceptance_criteria": ["..."],
    "owner": "person:alice"
  },
  "upstream": [
    {"node": "task:t0", "artifact": "resource-version:55", "sha256": "..."}
  ],
  "inputs": [
    {"name": "iris_data.csv", "path": "inputs/iris_data.csv", "sha256": "..."}
  ],
  "constraints": {
    "deterministic": true,
    "params": {"k": 3, "seed": 20261023, "split": "70/30"},
    "network": false,
    "language": "zh-CN"
  },
  "expected_outputs": [
    {"name": "report.md", "kind": "report"},
    {"name": "result.json", "kind": "data"}
  ],
  "provenance": {
    "execution_id": "exec-...",
    "collaborator_id": "agent:data-collaborator",
    "requested_by": "person:alice"
  }
}
```

指令模板（固定骨架，变量由协作者填）：

```text
你是 <discipline> 科研执行 agent。
目标：<task_node.title / goal>
必须满足的验收条件：<acceptance_criteria>
输入文件：<inputs，含绝对路径>
固定参数：<constraints.params>
输出要求：
1) 把最终报告写到 report.md；
2) 把结构化结果写到 result.json；
3) 不要修改输入文件；不要联网（除非任务明确允许）。
完成后列出所有产物路径和关键指标。
```

设计要点：

- **核心计算用固定脚本**：T1/T2 上传 `check_iris_input.py` / `run_iris_baseline.py`，指令里写死命令与参数。SciencePal 负责真实执行与留痕，LLM 只做编排与验收，避免结果漂移。
- **任务包哈希**：对 `map + inputs + constraints` 做 canonical JSON 哈希，同时写进指令与报告，证明“跑的是哪一版任务”。
- **验收前置**：`expected_outputs` 在发起前就写清楚；收产物时按清单核对，缺件即失败。
- **revision pinning**：任务包与候选都引用 `trigger_revision_id`；地图前进后提交候选会得到 `stale_base`，这是正确行为。

## 7. 端到端时序

```text
PO 发布正式图 rev-7（T1 → T2 → T3）
  → coordinator 发 task_handoff_ready(T1, rev-7, executor=agent:data-collaborator)
  → 协作者 get_formal_mapping_at_revision(rev-7)，取 T1 切片与上游引用
  → 组任务包，输入算 sha256
  → sciencepal_start(idempotency=exec:<execution_id>)
  → run_id / thread_id；ExecutionRecord=running
  → sciencepal_status 轮询（指数退避，20s 起）
  → completed → sciencepal_collect
  → 核对期望产物、sha256、验收条件
  → 生成 ExecutionReport（含 run_id、产物、指标、局限、建议变更集）
  → runtime 写中央草稿箱（kind=mapping_change，payload=报告+建议变更集）
  → TaskNode Owner 一审：接受 / 退回
  → 人调用 submit_candidate（base=rev-7）；如地图已前进，重新取基准
  → Centre Agent 预审 → PO 批准 → formalize → rev-8
  → 地图显示 T1 完成、T4 进入正式路线
  → coordinator 沿正式边触发 T2
```

协作者失败时：

```text
run failed / timeout / 缺产物 / 验收不满足
  → ExecutionRecord=failed（保留 run_id 与错误码）
  → 写失败报告草稿（不产生正式结果）
  → 需要改路线时，另起候选；普通失败不改正式图
```

## 8. 地图更新：两条轨道

这是整个设计最容易做错的地方。地图上的“进度”和“路线”必须分开：

| 轨道 | 内容 | 载体 | 是否进正式图 |
| --- | --- | --- | --- |
| 运行投影 | running / completed / failed、run_id、耗时 | ExecutionRecord + bridge run ledger | 否 |
| 路线变更 | 新节点/边、目标或验收条件变化、进度快照 | 草稿 → 候选 → 正式化 | 是 |

依据：`GLOSSARY.md` 与 `ai4-m0vt` / `ai4-r3so` 明确 running 状态属于运行投影，不得覆盖 TaskNode 的 `lifecycle_state`。`dashboard_source.py` 目前会从正式文档读 `execution_status`，那是演示夹具留下的口子，不应作为架构依据。

落地梯度：

- **L0（10/31 必做）**：地图只在正式化时变化。演示的“地图更新”= T4 进入正式路线 + T1/T2 的执行报告与 run 证据。运行中状态在协作者终端与报告里看，不假装实时。
- **L1（有余力）**：候选里带 `progress` 快照字段（节点状态、完成度、run_id），正式化后地图显示。明确标注“快照”，不是实时。
- **L2（赛后）**：新增 `task_progress` 事件 → coordinator 投影表 → 看板实时读取。这是正确形态，需要新消息类型、投影存储与看板适配，不在 4 天范围内。

## 9. 权限、审计与安全

- **令牌**：每个协作者一份 SciencePal token，放环境变量或系统密钥环；仓库只提交变量名。bridge 日志、错误、报告一律脱敏。
- **地图权限**：协作者令牌只开 `read`；`candidate_submit` 留给“推进候选”的人；`candidate_review` / `formalize` 永不下放。
- **文件边界**：bridge 只允许 `SCIENCEPAL_WORKSPACE` 下的文件；拒绝绝对路径逃逸、符号链接逃逸、超限文件。
- **草稿边界**：草稿箱当前只允许 `mapping_change`（`buffer/src/draft_buffer/service.py`）。执行报告作为 `mapping_change` 的 payload 提交，内含 `report` 与 `proposed_change_set`，避免改服务端 kind 白名单。
- **审计关联**：中央调用账本记录 MCP 调用（参数摘要）；SciencePal 调用不在账本内，因此 bridge 保存本地 run ledger，并把 `run_id`、产物 sha256 写进草稿 payload，形成跨系统弱引用。
- **数据合规**：只上传任务必需数据；遵守数据集许可证；敏感数据收集后显式清理沙箱；演示材料不出现令牌。

## 10. 落地计划（10/27–10/31）

| 日期 | 必须完成 | 产物 |
| --- | --- | --- |
| 10/27（今天） | 生成 token；SDK 冒烟：`agents.list`、带文件 `runs.initiate`、`runs.get`、`sandbox` 下载；确认输出目录、时长、失败形态 | 冒烟记录（run/thread id、产物清单） |
| 10/28 | bridge 四工具 + 单测（假 SDK）；Skill 初稿；`mcp.json`；协作者定义；T1 真跑通 | T1 报告 + 产物哈希 |
| 10/29 | 接入 runtime（MCP servers + skill instruction + 结构化报告写草稿）；T2 真跑通；缺列失败注入 | T2 报告 + 失败报告 |
| 10/30 | 草稿 → 候选 T4 → 正式化；演示脚本计时；证据卡与 5 页说明回填；录屏 | `iris_platform_pipeline` 新链路 + 视频 |
| 10/31 | 提交；链接自检；备份 | 提交材料 |

**Cut line**：

- 必须：SciencePal 真跑（至少 T1/T2）+ run_id/产物/哈希 + 报告草稿 + 正式图更新（T4）。
- 可选：runtime 自动 MCP 轮询、多协作者并行、L1 进度快照、SSE 实时进度。
- 砍掉：公网 MCP、SciencePal 自定义 Agent 回调、看板实时进度。

**兜底**：若 token/沙箱当天不可用，保留本机真实治理链路 + 预先录制的 SciencePal 运行录屏 + run 证据，如实标注，不用本机结果冒充 SciencePal 实演。

## 11. 备选：SciencePal 托管协作者（赛后）

SDK 的 `agents.create(system_prompt=..., custom_mcps=[...])` 表明平台侧支持把外部 MCP 挂给 SciencePal Agent。形态：

```text
SciencePal 自定义 Agent（角色 system_prompt）
  + custom_mcps = 中央 research-map MCP（read；可选 candidate_submit）
  + 领域内置工具 / sandbox
        ▲
        │ runs.initiate(agent_id=..., prompt=任务包)
        │
SciWeave conductor（读正式图、发任务、收结果、写草稿）
```

- 优点：更接近“多智能体在 SciencePal 里协作”，SciencePal 项目链接可直接作为参赛作品入口。
- 代价：中央 MCP 必须公网 HTTPS + Bearer；令牌轮换；候选权限与审计边界要重新划；调试黑盒。
- 建议：赛后先做只读版（Agent 只读地图，结果由 conductor 回写），验证 `custom_mcps` 字段形状后再决定是否下放 `candidate_submit`。

## 12. 赛事叙事与证据

一句话：**SciencePal 做科研，SciWeave 做协作与治理；地图是共享事实，不是聊天记录。**

证据链（每项都要能在评审时点开）：

1. SciencePal run：`thread_id` / `run_id`、发起时间、状态、耗时。
2. 输入：文件名 + sha256 + 上传记录。
3. 产物：`report.md` / `result.json` / 图表 + sha256 + 下载路径。
4. 执行报告草稿：`draft_id` + 一审结论。
5. 候选与正式化：`candidate_head`、diff、`formal_revision_id`。
6. 审计：中央调用账本查询结果 + bridge run ledger。

原创性与资源声明补充：SciencePal SDK（Apache-2.0）、官方 Skills 包（仅作参考实现，不直接再分发其脚本）、Iris（CC BY 4.0，署名）、本项目自研 bridge/skill/协作者定义。

## 13. 今天必须验证的清单

- [ ] token 可用；401 的返回形态
- [ ] `agents.list` 的内置 `agent_id` 与学科映射
- [ ] 带文件 `runs.initiate` 成功；文件落在沙箱哪个目录
- [ ] 输出目录约定；`report.md` 是否可写、在哪
- [ ] T1/T2 run 的典型时长（决定轮询与演示节奏）
- [ ] 失败 run 的 `status` / `error` 字段
- [ ] 沙箱根目录是否含系统文件，产物过滤规则
- [ ] SDK 在本机 Python 版本上的兼容
- [ ] 并发 run 限制
- [ ] 是否有可分享的 Replay/项目链接（证据用）

未完成这些验证前，不写“已集成”的结论；bridge 可以先按本文契约实现，用假 SDK 跑单测。

## 14. 当前实现（2026-10-27）

已落地，全部为新增文件，未改中央服务、未改现有 runtime：

| 位置 | 内容 |
| --- | --- |
| `custom-mcp/sciencepal-bridge/` | 独立 uv 子项目；HTTP 客户端、run ledger、5 个 MCP 工具、单测、smoke 脚本 |
| `libs/mcp-libs/sciencepal/mcp.json` | stdio 工具卡，已通过 runtime `mcp_resources` 校验 |
| `deploy-task-agent-skills/sciencepal-research/` | Skill 与任务包/证据参考 |
| `agent-definitions/agents/*-collaborator.yaml` | data / biology / materials 三个协作者定义 |
| `.env`（gitignored） | `SCIENCEPAL_ACCESS_TOKEN` 占位，等待替换 |

验证结果：

```text
uv run python -m unittest discover -s tests -v   # 11 项通过
MCP tools: sciencepal_start, sciencepal_status, sciencepal_collect, sciencepal_cancel, sciencepal_agents
```

未完成：

- runtime 尚未把 `sciencepal` MCP 挂给协作者（需要 `SCIEWEAVE_SCIENCEPAL_KIT=1` 的 opt-in 改动）；
- 尚未用真实 token 跑过 SciencePal（等 token 后先跑 `scripts/smoke.py`）；
- 草稿 payload 仍是 `{result_summary}`，尚未接结构化 ExecutionReport。

下一步顺序：真实 smoke → 按实际输出目录调整 `collect` → runtime opt-in → 草稿结构化。
