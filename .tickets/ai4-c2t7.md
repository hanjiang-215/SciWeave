---
id: ai4-c2t7
status: closed
deps: []
links: [ai4-xup8]
created: 2026-10-20T06:31:26Z
type: task
priority: 1
assignee: hanjiang
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# Task Agent 初始化所需的 Mapping 查询契约

## Question

当 Mapping 开发完成并提供查询能力后，确定 Task Agent 初始化时读取 TaskNode、Task Owner、必要上游与配置版本所需的最小只读查询契约。该票只定义消费端需要的请求前置条件、响应字段、版本标识、空结果与不可用错误语义；不设计 Mapping 写入、运行期回调或领域 Buffer。

> 修订（2026-10-21）：端侧 agent 被设计为**持有自己的 MCP 客户端、可随时只读查询地图**，因此原文「运行期不依赖 Mapping 查询」不再成立。新的边界：初始化必须查询一次并持久化快照（供订阅与隔离使用）；运行期**允许**只读查询以获取上下文，但必须定义中央 Mapping 不可用时的降级行为。

## Design（2026-10-25 收口）

### 查询能力与输入前置条件

端侧 Task Agent 凭主体身份调用 **research-map 管理 MCP**（Bearer token → actor 注入，`read`/`centre` 档），初始化时做**一次**只读查询并持久化快照到端侧；运行期允许再次只读查询获取上下文。工具面取最小子集：

- `get_formal_mapping`（`mapping_domain_id`）：读取当前正式 Mapping 图，返回 `formal_revision_id`、`store_id`、`branch_id`、`commit_hash`、`content_digest` 与 `documents`（TaskNode/DependencyEdge 数组）。
- `get_formal_mapping_at_revision`（`mapping_domain_id` + `formal_revision_id`）：读取指定正式版本的精确快照，用于与交接消息携带的版本对齐（`ai4-2982` 已定）。
- `list_candidates`（`submission_id`）：读取单个候选记录。
- `list_reviewable_candidates`（`mapping_domain_id`）：读取全部可送审候选（未合并/未驳回/未放弃）的固定 head、正式基准、提交者与状态。

### 响应字段与版本标识

Task Agent 初始化快照至少需要：

- TaskNode 字段：`logical_id`、`version_id`、`task_owner_id`、`executor_refs`（`ai4-0s02`：直接引用 Workflow Agent 稳定 `agent_id`）、状态与 `proposal_id`；
- 必要上游：`DependencyEdge` 的 `logical_id`/`version_id`/目标与源引用，用于激活条件判断；
- 配置版本：`formal_revision_id` + `content_digest` 一并持久化，后续只读查询或订阅对账时用版本标识判断快照是否过期。

身份（负责哪个 TaskNode）由**配置项 + 提示词**双重表达，不由提示词单独承载（2026-10-21 已定）。

### 错误语义与降级行为

MCP 调用返回稳定错误分层：`invalid_arguments`（参数缺/错）→ `denied`（无 read/centre 权限，HTTP 401 为未认证）→ `no_such_revision`/`inconsistent`/`unavailable`（领域语义）→ `audit_unavailable`（审计库不可用）。Task Agent 处置：

- **空结果**（`no_formal_revision`）：初始化失败并上报，不创建执行快照；
- **未授权**（`denied`）：初始化失败并上报，视为配置/登记问题，不重试；
- **暂不可用**（`unavailable`）：沿用已有快照继续执行并标记降级，或阻塞并上报——按运行期策略选择，必须显式记录降级状态；
- **版本不兼容**（快照 `formal_revision_id` 与交接消息目标版本不一致）：以交接消息携带的 `formal_revision_id` 为准重新拉取快照；拉取失败则阻塞并上报，不静默执行旧版本任务。

### 边界

不引入 Mapping 写入、领域 Buffer 或运行期回调；快照只读持久化在端侧，不写回中央领域存储。

## Acceptance Criteria

- [x] 确认由 Mapping 提供的最小只读初始化查询能力及其输入前置条件
- [x] 明确 Task Agent 必需的 TaskNode、Task Owner、必要上游与配置版本字段
- [x] 明确空结果、未授权、暂不可用和版本不兼容的错误语义
- [x] 不引入 Mapping 写入、领域 Buffer 或运行期回调
- [x] 初始化必须查询并持久化快照；运行期允许只读查询；须定义只读查询不可用时的降级行为（沿用快照继续执行，或阻塞并上报）

> 修订（2026-10-21）：删去原文「仅在显式初始化时查询并持久化快照，运行期不依赖 Mapping 查询」。改为：初始化查询并持久化快照；运行期允许只读查询；须定义只读查询不可用时的降级行为（例如沿用快照继续执行，或阻塞并上报）。

## Notes

**2026-10-25 收口与关闭（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

契约收口依据真实落地的 research-map 管理 MCP 工具面：

- 查询能力最小子集已全部实现：`get_formal_mapping`（当前正式）、`get_formal_mapping_at_revision`（按版本精确快照，`ai4-2982` 新落地）、`list_candidates`、`list_reviewable_candidates`（`ai4-he04`/`ai4-5z9e` 输入端）。
- 错误语义沿用 `ai4-w73z` 稳定分层（invalid_arguments/denied/领域语义/audit_unavailable），`no_formal_revision`、`no_such_revision`、`inconsistent`、`unavailable` 逐一有处置；版本不一致以交接消息 `formal_revision_id` 为准重拉，拉取失败阻塞上报。
- 字段来源：TaskNode Owner 与依赖边字段模型（`ai4-t5zl`/`ai4-r3so`）、`executor_refs` 直接引用 Workflow Agent `agent_id`（`ai4-0s02`），均已关闭。
- 依赖解除：原 deps `ai4-xup8` 改为 links。原因：本票所需的是 Mapping **查询契约**，其子分支规格（持久化模型 `yl2o`/`56iu`、访问边界 `9322`、查阅语义 `w73z`/`2982`）均已关闭；xup8 地图剩余开放的是消息协作（te1v）与端侧 Agent 分支（kpvp，Frank Qi），与端侧初始化查询契约无阻塞关系。
- 本票只定义契约，不实现端侧 Task Agent runtime；落地由 `ai4-za77`（建立新 Task Agent 的套件，Frank Qi）侧消费。

验收五项全部勾选，置 `closed`。

**2026-10-25 负责人转交（hanjiang 操作，经 Frank Qi 授权）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据 Gitee issue https://gitee.com/qi-yueran/ai4science/issues/IKQ8BD 第 1 条，Frank Qi 授权 hanjiang 直接转交。转交原因：本票阻塞于 `ai4-xup8`（hanjiang 地图），且契约所需的 `list_candidates`/`list_reviewable_candidates` 只读工具已由 hanjiang 实现，转由 hanjiang 承接最顺。正文与验收标准不改写，仅变更归属并记录。

**2026-10-21T13:10:19Z**

2026-10-21T21:14:00Z

消费端位置变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)：本票定义的初始化只读查询契约仍然成立，但请求方从「中央 Gateway」变为「研究员电脑上的端侧 agent」。

对本票的影响：

- 查询调用方是端侧进程，凭主体身份调用中央 Mapping 管理 MCP，需要经过「端侧 Agent 的 MCP 能力注册与限制」(ai4-ujvn) 的主体校验。
- 「仅在显式初始化时查询并持久化快照」这条仍然成立，快照留在端侧。
- 空结果、未授权、暂不可用、版本不兼容四种错误语义不变。
- 解除对 ai4-xup8 的依赖关系待复盘：本票原本等 Mapping 领域规格收敛，该依赖仍然有效，无需改动。

本票仍 open。

**2026-10-21T14:58:58Z**

2026-10-21T22:58:00Z

推翻上述 2026-10-21T21:14:00Z 的一条：原文说「本票原本等 Mapping 领域规格收敛，该依赖仍然有效」，同时按旧设计写「运行期不依赖 Mapping 查询」。

2026-10-21 第四轮讨论确认：端侧 agent 会有自己的 MCP 客户端，可以查地图；构建 fast-agent 时提示词会告知它负责哪个任务节点。因此运行期只读查询是允许的。

本票据此改写正文与验收标准：

- 初始化必须查询并持久化快照（保留）。
- 运行期允许只读查询（新增）。
- 需要定义只读查询不可用时的降级行为（新增）。
- 身份（负责哪个 TaskNode）由配置项与提示词双重表达，不由提示词单独承载。

依赖 ai4-xup8 保持不变，仍在等 Mapping 领域规格暴露只读查询接口。
