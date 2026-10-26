# AI4Sci / SciWeave 项目审查

> 说明（2026-10-27）：本文是 2026-10-22 的时点快照，其中的“未实现”“测试失败”等数字与结论此后已经变化。当前状态以 `docs/` 与 `.tickets/` 为准，本文正文不再更新。

- 审查日期：2026-10-22
- 审查对象：`d:\project\AI4Sci`（分支 `feature/hanjiang`，HEAD `e4e0a93`，工作区干净）
- 审查方式：读仓库结构、文档与工单；实跑各子项目测试；抽查关键源码与配置；检索硬编码、桩代码与重复定义
- 说明：本文不进入仓库，路径均相对项目根

---

## 一、结论摘要

1. **文档与规格体系是这个项目最强的资产，代码只覆盖了其中一小块。** 105 张工单、术语表、ADR、data-flow 与交付设计互相咬合，`ticket_index.py check` 通过；但可运行代码只有“两个领域的治理内核 + 一个已过期的 Gateway”，中央草稿箱、领域 MCP、中央 Agent、注册表、Web 看板、Agent 套件全部未实现。
2. **task-agent 的 Gateway 今天已被自己的 ADR 推翻。** `docs/adr/0001-task-dispatch-via-message-queue.md` 与 `docs/data-flow/work-agent.md`（均 2026-10-22）把形态改为“消息队列下发 + MCP 只做处置 + 三组件（mcp/subscriber/worker）”，而当前代码仍是 `submit_owner_command` 的旧形态，且没有 subscriber。继续在这套代码上加功能是负收益。
3. **task-agent 的 20 个测试在本机 16 个失败，根因已定位**：测试把等待上限写死 2 秒，而 worker 子进程需要导入整个 `gateway.app`（连带 fast-agent 运行时栈），本机实测约 5–6 秒。我实证：把等待上限改为 60 秒后同一用例 5.2 秒通过。这是测试与进程划分问题，不是业务逻辑错误。
4. **距作品提交只剩 9 天（10/31 截止，10/24 报名截止），而端到端演示链路不存在。** 两个领域服务没有任何 MCP/HTTP 入口，没有草稿箱，Task Agent 的执行结果无处可写。当前最该做的是打通一条纵向切片，不是继续补规格。
5. **规划缺口比代码缺口更急**：`ai4-z3z4`（最小 Work Agent 实现规格）写明自己是“后续实现 tickets 的唯一上游输入”，`ai4-xem8`（草稿箱契约）也是规格票——但对应的实现票还没建。9 天里团队手上没有可直接开工的建设票。

---

## 二、实测结果

### 2.1 测试

命令见附录。结果为 2026-10-22 在本机（Windows，Python 3.14.5，uv 0.10.7）实测。

| 子项目 | 源码行数 | 测试行数 | 实测结果 | 备注 |
| --- | ---: | ---: | --- | --- |
| `sci-weave/centre-control/research-map` | 1838 | 1524 | 74 项，全部通过（5 跳过） | 跳过项为需真实 TerminusDB 的集成测试 |
| `sci-weave/centre-control/research-wiki` | 2114 | 2184 | 73 项，全部通过（4 跳过） | 同上；另有 12 个集成测试仅在显式开关下收集 |
| `sci-weave/shared/audit-trail` | 227 | 109 | 11 项全部通过 | 无任何调用方引用该包 |
| `sci-weave/task-agent`（worker） | 876 | 483 | 4 项通过 | 仅覆盖配置校验，不含 loop |
| `sci-weave/task-agent`（gateway/mcp） | 同上 | 同上 | 20 项中 16 项失败 | 见 2.3 根因 |
| `sci-weave/task-agent`（gateway/ingest） | 4 | 0 | 无测试 | `cli.py` 直接 `SystemExit("not implemented yet")` |

`docs/tickets` 的索引一致性校验通过：`OK：105 张工单，7 个模块，生成文件一致。`

### 2.2 工单

- 总数 105：open 28 / in_progress 3 / closed 74；活跃 31 张，地图 7 张。
- 负责人分布（活跃）：Frank Qi 25 张（open 24 / in_progress 1）、hanjiang 5 张、未分配 1 张。
- 风险：**25/31 的活跃工单压在一个人身上**，而两个已实现的领域由另一人负责，交接与并行度都受限。

### 2.3 Gateway 测试失败的根因（已复现）

- 现象：16 项失败均为 `execution ... did not reach <status>`，子进程打印 `sqlite3.OperationalError: unable to open database file`。
- 定位：
  - `sci-weave/task-agent/gateway/mcp/tests/test_gateway.py:195`：`deadline = time.monotonic() + 2`，固定 2 秒。
  - `sci-weave/task-agent/gateway/mcp/src/gateway/app.py:122` 起，用 `multiprocessing.get_context("spawn")` 起 worker，目标是同模块的 `run_worker_process`。
  - 实测 `import gateway.app` 冷启动 **6.06 秒**；spawn 一个子进程并 join **5.56 秒**。
- 因果链：子进程还在导入模块时，父测试已超时失败 → `tearDown` 删除临时目录 → 子进程随后 `sqlite3.connect()` 找不到目录，报 “unable to open database file”。
- 验证：把 `wait_for_execution` 的超时临时改为 60 秒后，`test_test_runtime_completes_queued_execution_through_a_short_lived_worker` 在 5.2 秒内通过。
- 结论：业务状态机没有坏；坏的是“worker 入口 = 整个 HTTP 应用模块”的划分，以及测试里的硬编码超时。修法见第五节。

---

## 三、目录与文件位置

### 3.1 合理的部分

- `sci-weave/centre-control/` 下每个目录是独立子项目，各自持有 `pyproject.toml`、`uv.lock`、`.env.example`、`src/`、`tests/`，符合项目规范中“独立部署角色即子项目”的定义。
- `sci-weave/service/<服务名>/` 放 TerminusDB 与 Redpanda 的 compose，与业务项目分属不同部署单元，符合规则。
- `sci-weave/task-agent/` 使用 uv workspace，组级唯一 `uv.lock`，三个角色各自 `pyproject.toml`，符合“项目组”约定。
- 配置纪律好：源码不含硬编码地址/端口，`.env.example` 用 `PORT` 占位，测试用回环地址与临时端口 `0`。检索确认代码中无 `127.0.0.1:6363` 之类硬编码。

### 3.2 需要收拾的部分

| # | 位置 | 问题 | 建议 |
| --- | --- | --- | --- |
| 1 | `sci-weave/llm-wiki/`、`sci-weave/research-mapping/`、`sci-weave/gateway/` | 项目已迁到 `centre-control/`（提交 `18b220a`），这三个目录只剩 `.venv`、`__pycache__`、`egg-info`，无任何源码 | 直接删除。虽被 `.gitignore` 覆盖不影响仓库，但会误导导航与 IDE 索引 |
| 2 | `sci-weave/shared/audit-trail/` | 现行规则明确“不再设顶层 `sci-weave/shared/`”，该包应属 `centre-control/shared/`；迁移票 `ai4-gvan` 仍 open | 按 `ai4-gvan` 迁移；同时接受“迁移前文档先写”的事实 |
| 3 | `sci-weave/centre-control/README.md` | 已按迁移后的位置把 `shared/audit-trail` 写进 `centre-control` 表内，与实际位置不符 | 迁移完成前改回实际路径，或标注“待迁移” |
| 4 | `docs/superpowers/specs/2026-10-21-mapping-wiki-formalization-delivery-design.md` | 写 TerminusDB 验证服务在 `sci-weave/centre-control/terminusdb/`，实际在 `sci-weave/service/terminusdb/` | 修正路径 |
| 5 | `.tickets/ai4-txhf.md` 的 Implementation Contract | 写代码位置 `sci-weave/llm-wiki/src/llm_wiki/candidate_submission.py`，实际在 `centre-control/research-wiki/` | 由该票 assignee 修正 |
| 6 | `sci-weave/centre-control/registery/` | 目录名拼写错误（应为 registry） | 现在只有 README，改名成本最低，越晚越贵 |
| 7 | `sci-weave/task-agent/` 组根 | 规则要求项目组根有 `Dockerfile`、`compose.yaml`，当前只有 `pyproject.toml`/`uv.lock`/README；README 已说明“常驻角色具备实际启动行为后再添加” | 可接受，但应登记为待办，避免被当成已完成 |
| 8 | `sci-weave/centre-control/research-map/README.md` | 目录清单里 `sqlite_store.py`、`terminus_store.py` 各列了两次；文末重复一段命令块；开头仍自称“正式版本查询切片” | 更新为当前模块全集 |
| 9 | `sci-weave/centre-control/research-wiki/README.md` | 仍只描述“资源资格审核切片”，未提已有的 `candidate_submission.py`、`review.py`、`formalization.py`、`formal_query.py` | 补目录与运行方式 |
| 10 | 项目根 `.pytest_cache/` | 本地残留 | 删除；如需长期使用，把 `.pytest_cache/` 加进 `.gitignore` |

### 3.3 命名与结构的一致性

- 目录名表达部署角色（`research-map`、`research-wiki`），模块名简洁（`research_mapping`、`llm_wiki`），符合规范。
- `centre-control/` 被定义为“只表示部署在中央服务器”，内部各项目不共用锁文件，与实际一致。
- `docs/tickets/INDEX.md` 与 `modules/*.md` 是生成物且被忽略，`meta/` 与 `modules.toml` 入库，索引可重建——这一套设计是健康的。

---

## 四、代码与架构的偏差

### 4.1 最严重：Gateway 已经不符合现行架构

`docs/adr/0001-task-dispatch-via-message-queue.md`（accepted，2026-10-22）与 `docs/data-flow/work-agent.md` 规定：

- 任务下发只经消息队列；MCP 只承接返修、放弃、转人工、回答提问、观察、取消；
- 组件为 `gateway/mcp`、`gateway/subscriber`、`worker`，三者共享同一 SQLite 与状态机；
- 状态机只有 `queued → running → {waiting, completed, needs_revision, rejected, human_takeover, failed, cancelled}`，**没有 `blocked`、`awaiting_acceptance`、`accepted`**；
- 执行结果由 Worker 内的 agent 写入中央草稿箱，Gateway 只记 `draft_id`。

当前代码：

- `gateway/mcp/src/gateway/app.py:160` 定义 `submit_owner_command`，`:457`、`:519` 暴露为 MCP 工具；
- `app.py:84`、`:304` 使用 `awaiting_acceptance`；`app.py:258` 的待处理列表仍含 `blocked`；
- 没有 `gateway/subscriber`，没有 `answer_question`，没有 `draft_id`；
- 20 个测试围绕旧形态编写。

`sci-weave/task-agent/README.md` 已如实写明“实现仍按旧形态写，尚未改造”。这是好习惯，但也意味着**这些测试的价值会在重写时归零**。

### 4.2 已经写好、但没人用的东西

`shared/audit-trail` 有完整实现与 11 个测试，但全仓库除自身与 `centre-control/README.md` 外没有任何引用；两个领域的 `pyproject.toml` 依赖都是空数组。它不是“完成了的模块”，是“提前铺好的地基”——在中央接口层出现之前，接入它只会空转。

### 4.3 领域服务的形态

- `research-map`：候选提交、审阅、正式化、正式查询、失败恢复齐全，边界（SQLite 治理 + TerminusDB 精确 Commit）实现得相当克制。
- `research-wiki`：在 Mapping 之上多了资源资格审核与撤回，同样完整。
- 但两者都**只是进程内服务类**。`src/main.py` 是演示 CLI（查一个正式版本 / 查一个资源资格），没有任何 MCP、HTTP、任务队列入口。全仓检索 `FastAPI`/`HTTPServer`/`mcp` 在 `centre-control/` 下无命中（除 README）。
- 两个领域的同名模块（`canonical.py` 完全一致；`config.py`、`errors.py`、`sqlite_store.py`、`terminus_store.py`、`review.py`、`formalization.py` 结构相似但内容各自演化）——符合术语表“治理语义可共用、实现与存储独立”的裁决，不算缺陷；但约 4000 行里存在重复的幂等/激活模式，若后续要加第三个领域，需要一次明确的“共用内核”决策。

### 4.4 具体代码缺陷

1. **同名测试方法覆盖**：`sci-weave/centre-control/research-wiki/tests/test_formalization.py:63` 与 `:101` 都叫 `test_same_operation_is_rejected_when_owner_approval_identity_changes`。后者覆盖前者，前者（包含通知失败、`formalization_activated` 审计断言）**永不执行**。
2. **读回失败被吞掉**：`research-wiki/src/llm_wiki/candidate_submission.py:202` 的 `except Exception: pass` 在重新物化候选结果时忽略读回异常，仍返回 `confirmed`。该提交此前已确认并持久化，所以不影响治理状态，但返回的引用列表可能为空，与“confirmed 表示读回验证过”的语义有落差，建议至少记录原因码。
3. **测试数量与票面证据不一致**：`ai4-txhf` 的记录写“82 项全部通过”，当前 HEAD 实跑 73 项；差异来自 12 个需显式开启的 TerminusDB 集成测试与 1 个被覆盖的同名测试（86 − 12 − 1 = 73）。不是功能回退，但验收证据需要按当前 HEAD 重新记录。

### 4.5 流程一致性

`docs/superpowers/specs/2026-10-21-mapping-wiki-formalization-delivery-design.md` 的状态仍是“待用户审阅”，而它描述的 Mapping/Wiki 实现已经合并进 `develop`（提交 `19d8d20`）。设计文档与代码的评审状态脱节，后续读文档的人无法判断“这是已批准方案还是提案”。

---

## 五、模块完成度

| 模块 | 状态 | 依据 | 还缺什么 |
| --- | --- | --- | --- |
| Research Mapping 领域（治理内核） | **完成** | 4 张实现票 closed；74 项测试通过；真实 TerminusDB 集成测试可显式运行 | 对外 MCP 入口；候选提交的命令行/服务封装 |
| LLM-Wiki 领域（治理内核） | **基本完成** | 5 张实现票中 4 张 closed；73 项测试通过 | `ai4-txhf` 需按 HEAD 重新验收并关闭；对外 MCP 入口 |
| 统一留痕包 | **完成但未接入** | 11 项测试通过 | 迁移到 `centre-control/shared/`；接口层出现后接入 |
| Task Agent Gateway（MCP 处置面） | **过期** | 20 项测试中 16 项本机失败；形态与 ADR 冲突 | 按新架构重写：删 `submit_owner_command`，加 `answer_question`、`draft_id`、`completed` |
| Task Agent 消息监听（subscriber） | **未开始** | 目录不存在 | 消费 Redpanda、按 `task_node_id` 落 Execution Record、持 consumer group 与 offset |
| Task Agent ingest | **桩** | `cli.py` 直接 `SystemExit` | 与 subscriber 合并或明确其边界 |
| Task Agent worker loop | **骨架** | 只有配置校验；运行时适配器存在 | 一轮 fast-agent loop、会话恢复、把结果写草稿 |
| 中央草稿箱（buffer） | **未开始** | 只有 README；`ai4-xem8` 是契约票 | 最小服务 + 7 件 MCP 工具 + 两命名空间 |
| 中央 Agent（centre-agents） | **未开始** | 只有 README | 候选预审、报告追加、混合候选 |
| 注册表（registery） | **未开始** | 只有 README | 主体与端侧 Agent 登记；目录名先改正 |
| Web 看板（web-ui） | **未开始** | 只有 README，无 `package.json` | 只读看板；正式查询与执行记录的可视化 |
| Agent 套件（toolkits） | **未开始** | 四个目录只有 README | 套件格式、安装流程、示例 |
| 演示场景（`ai4-aaff`） | **in_progress，证据为空** | 场景与流程已定（UCI Iris） | SciencePal 真实执行证据、计时视频、5 页说明、审计轨迹 |

规划层面的缺口：`ai4-z3z4`（Work Agent 实现规格）自称是后续实现的唯一上游，`ai4-xem8`（草稿箱契约）同样只有规格，**两者都还没有下游实现票**。这是当前最需要立刻补的“可开工性”。

---

## 六、风险清单（按影响排序）

1. **演示链路不存在**（10/31 截止）：领域服务无入口、无草稿箱、无看板，无法在 3–5 分钟内演示“提交 → 候选 → 审批 → 正式化 → 查询”。
2. **架构重写成本被低估**：Gateway 重写会作废 20 个测试与现有 MCP 工具面，且订阅器依赖尚未定型的消息语义（`ai4-te1v` open）。
3. **没有 CI**：全仓无 `.github/`、`.gitee/`、任何流水线配置；集成测试默认跳过。“真实服务通过”只存在于个人机器的环境变量里，提交前无法自动回归。
4. **验证证据与 HEAD 容易脱节**：`ai4-txhf` 的 82 项与当前 73 项即为实例。
5. **单点负载**：25/31 活跃工单压在一人身上。
6. **文件路径漂移**：旧目录残留、设计文档与票中的旧路径，会让下一个按票施工的 agent 走错地方。
7. **TerminusDB 与 Redpanda 只有本机单节点**：生产形态（副本、保留期、暴露方式）在 `docs/TECH_STACK.md` 中仍列为未确定项。

---

## 七、推进建议

### 7.1 立刻做（第 1 天）

1. **修测试可靠性**（不改变业务）：
   - 把 worker 入口拆成独立轻量模块（例如 `gateway/worker_entry.py`），只导入 SQLite 与 Runtime Adapter，不导入 HTTP/MCP/服务器代码；`app.py` 只负责起进程。这一步同时把每次执行的 5–6 秒冷启动降下来。
   - `wait_for_execution` 改为可配置超时（默认 ≥30 秒），并在断言失败信息里带上子进程状态。
   - 修 `test_formalization.py` 的同名测试（合并或改名），确认通知失败与审计断言真正执行。
2. **清目录**：删除 `sci-weave/llm-wiki`、`sci-weave/research-mapping`、`sci-weave/gateway` 与根 `.pytest_cache`；`registery` 改名。
3. **修文档路径**：交付设计与 `ai4-txhf` 的代码位置、`centre-control/README.md` 的 `shared/audit-trail`、两个领域 README 的目录清单。
4. **补可开工性**：由对应 assignee 建两张实现票——草稿箱最小服务、领域管理 MCP（先做 Wiki 或 Mapping 之一）。工单修改权归 assignee，需协调后再动。

### 7.2 打通一条纵向链路（第 2–4 天）

选一个域先做（建议 Wiki：资源资格审核已闭环，链路更短），目标是能在 3 分钟内演示：

```
草稿箱 create_draft → 领域 MCP submit_candidate → 候选预览 → 审阅
→ Owner 批准 → 正式化 → 正式查询返回精确版本
```

验收标准建议：一条命令启动服务；一条脚本跑完整条链；失败路径（基准过期、候选头变化、资源撤回）至少各演示一次。

### 7.3 按新架构重写 Task Agent（第 5–6 天）

按 `docs/data-flow/work-agent.md` 落地最小实现：subscriber 消费 Redpanda → 单事务写 `queued` 记录 → 领 Worker Lease → worker 跑一轮 → 结果写草稿 → `completed(draft_id)`。旧代码在新链路跑通后再删，避免演示前夜无可运行版本。

### 7.4 展示与交付（第 7–9 天）

- 只读 Web 看板：正式链接、Wiki 版本、Execution Record 状态与阻塞点。
- `ai4-aaff` 缺的证据：SciencePal 真实执行记录、3–5 分钟计时视频、5 页以内说明、原创性与第三方资源声明、获批/驳回的真实审计轨迹。

### 7.5 可以推迟到演示之后

- `ai4-gvan` 留痕迁移与接口层接入（先有接口层再接，否则空转）。
- 两个领域治理内核的“共用化”重构。
- 生产部署、容器编排、密钥管理。

---

## 八、附录：复现命令

以下命令在项目根执行；Python 子项目各自使用 `uv`。

```powershell
# 领域测试
cd sci-weave\centre-control\research-map;  uv run --locked python -m unittest discover -s tests
cd sci-weave\centre-control\research-wiki; uv run --locked python -m unittest discover -s tests
cd sci-weave\shared\audit-trail;           uv run --locked python -m unittest discover -s tests

# Task Agent
cd sci-weave\task-agent; uv run --locked python -m unittest discover -s worker/tests
cd sci-weave\task-agent; uv run --locked --package sciweave-task-agent-gateway-mcp `
  python -m unittest discover -s gateway/mcp/tests

# 工单索引一致性
python .cursor\skills\engineering\ticket-index\scripts\ticket_index.py check
```

真实 TerminusDB 集成测试需显式开启（以 Wiki 为例）：

```powershell
$env:SCIWEAVE_RUN_TERMINUSDB_INTEGRATION = "1"
$env:SCIWEAVE_WIKI_TERMINUSDB_URL = "http://127.0.0.1:6363"
$env:SCIWEAVE_WIKI_TERMINUSDB_STORE = "<store>"
$env:SCIWEAVE_WIKI_TERMINUSDB_DATABASE = "<database>"
$env:SCIWEAVE_WIKI_TERMINUSDB_USERNAME = "admin"
$env:SCIWEAVE_WIKI_TERMINUSDB_PASSWORD = "<store-key>"
uv run --locked python -m unittest discover -s tests -p "test_*integration.py" -v
```

---

## 九、本次审查的局限

1. 未运行真实 TerminusDB 集成测试（本机未启动服务），因此“与真实存储的边界”依赖票面证据，而非我本轮复现。
2. 未审计安全边界（令牌校验、跨域授权）以外的实现细节；Gateway 的鉴权只做了代码阅读，未做渗透式验证。
3. 未评估 SciencePal 平台侧能力，`ai4-aaff` 的可行性依赖赛事方环境。
4. 未修改仓库任何文件；本次审查未执行任何票务变更，工单结论以 `assignee` 的更新为准。
