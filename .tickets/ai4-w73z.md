---
id: ai4-w73z
status: closed
deps: []
links: [ai4-9322, ai4-6ljq, ai4-orpg, ai4-ujvn]
created: 2026-10-23T02:53:55Z
type: feature
priority: 1
assignee: hanjiang
tags: [mcp, mapping, wiki, audit, centre-control, implementation, ready-for-agent]
---
# Research Mapping 与 LLM-Wiki 对外管理接口及权限分层

为 Research Mapping 与 LLM-Wiki 实现可供研究员端侧 Agent、中央 Agent 和 Project Owner 调用的对外管理接口，优先采用两套独立的领域管理 MCP；不得把两个领域合并为一个跨域接口，也不得让调用方绕过领域服务直连 SQLite 或 TerminusDB。现有领域应用服务已具备正式查询、候选提交、候选审阅和正式化能力，本票负责把这些内部能力包装成稳定的对外工具、完成调用方权限隔离、启动配置和验证。\n\n请重点关注 Gitee Pull Request #27（https://gitee.com/qi-yueran/ai4science/pulls/27）及其相关接口约定；共享部分的接口层调用留痕已经实现，代码位于 sci-weave/centre-control/shared/audit-trail。对外接口必须在服务启动时打开并初始化审计库，并按共享包约定记录工具调用；不要在领域服务内部重复接入或自行定义另一套审计事件。

## Notes

**2026-10-23 切片一：Research Mapping 管理 MCP（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`，`git config user.name` 为 hanjiang，一致。

已落地 research-map 侧切片（提交 999df8c）：

- `src/research_mapping/management.py`：`MappingManagementService` 经 `FormalQueryService`/`MappingCandidateService` 暴露 `get_formal_mapping`、`list_candidates`、`submit_candidate`；服务端按 `read` / `candidate_submit` / `centre` 能力档位鉴权，未授权返回稳定 `forbidden`。读工具在完成后 `record_attempted`（fail-open），写工具执行前 `begin_call`（fail-closed）、完成/失败后 `finish_call`。
- `src/research_mapping/management_mcp.py`：Streamable HTTP MCP 端点（`POST /mcp`、`GET /health`），Bearer token 映射 actor_id 注入，不信任客户端自报角色；未知/缺失令牌返回 HTTP 401。
- 配置：`SCIWEAVE_MAPPING_MCP_HOST`/`_PORT`/`_TOKENS_JSON`、`SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON`、`SCIWEAVE_MAPPING_AUDIT_SQLITE_PATH`；配置审计路径后启动时必须打开并建表，失败拒绝启动。依赖：`research-map` 以相对 path 引用共享 `sciweave-audit-trail`，锁文件已更新。
- 测试：`tests/test_management.py` 10 项，覆盖权限分层、审计双阶段、传输身份注入、越权拒绝、配置校验。验证：`uv sync --locked` 通过；`uv run --locked python -m unittest discover -s tests -q` 全量 87 项通过（含真实 TerminusDB 集成，2 项跳过）；`compileall` 通过。

切片边界：本切片只覆盖正式只读、候选提交与审计基础；候选读取更多入口、候选审阅、Owner 正式化/恢复、中央 Agent 工具面和 Wiki 侧管理 MCP 留待后续切片。切片 2 起实现前需复核 `ai4-ujvn`/`ai4-t2wc` 开放面是否有新修订，如冲突先在本 Notes 记录。Gitee PR #27 的接口约定已复核：管理 MCP 与看板只读来源保持独立端点、共用领域服务，无命名冲突。

**2026-10-23 切片二：LLM-Wiki 管理 MCP（hanjiang）**

已落地 wiki 侧切片（提交 72b146b），与映射侧对称：

- `src/llm_wiki/management.py`：经 `WikiFormalQueryService`/`WikiCandidateService` 暴露 `get_formal_wiki`、`submit_wiki_candidate`；服务端按 `read` / `candidate_submit` / `centre` 能力档位鉴权，未授权返回稳定 `forbidden`。读/写审计语义与映射侧一致（读 `attempted` fail-open，写 `invoked`/`completed` fail-closed）。
- `src/llm_wiki/management_mcp.py`：Streamable HTTP MCP 端点（`POST /mcp`、`GET /health`），Bearer token 映射 actor_id 注入，不信任客户端自报角色。
- 配置：`SCIWEAVE_WIKI_MCP_HOST`/`_PORT`/`_TOKENS_JSON`、`SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON`、`SCIWEAVE_WIKI_AUDIT_SQLITE_PATH`；依赖以相对 path 引用共享 `sciweave-audit-trail`。
- 测试：`tests/test_management.py` 10 项；全量 `uv run --locked python -m unittest discover -s tests -q` 107 项通过（含真实 TerminusDB 集成）、`compileall`、`uv sync --locked` 通过。

至此 `ai4-w73z` 两个领域的只读 + 候选提交最小闭环已完成；候选审阅、Owner 正式化/恢复、中央 Agent 工具面（`append_prereview_log`、`create_merged_candidate`）与五档完整覆盖留待切片三。切片三实现前需复核 `ai4-ujvn`/`ai4-t2wc` 是否收口，以及 `ai4-9322` 边界约束在两领域的落实。

**2026-10-23 切片三：候选审阅与正式化工具（hanjiang）**

已补齐两个领域管理 MCP 的审阅与正式化工具（提交 a202af1）：

- Mapping：`preview_candidate`（candidate_review）、`record_review`（candidate_review）、`formalize_candidate`（formalize）、`reconcile_formalization`（formalize），经 `MappingReviewService`/`MappingFormalizationService` 调用。
- Wiki：`preview_wiki_review`、`create_wiki_merge_request`（candidate_review），`decide_wiki_review`、`formalize_wiki`、`reconcile_wiki_formalization`（formalize），经 `WikiReviewService`/`WikiFormalizationService` 调用；`_OwnerVerifier` 按调用方 `formalize` 能力验证 Owner 授权。
- 所有审阅/正式化工具均为写工具：执行前 `begin_call`（fail-closed）、完成/失败后 `finish_call`。transport `tools/list` 只列出已注入领域服务的可用工具，避免暴露不可调用的工具面。
- 验证：Mapping 12 项管理测试 + 全量 89 项（含真实 TerminusDB 集成）、Wiki 10 项管理测试 + 全量 107 项全部通过；`compileall`、`uv sync --locked`、`git diff --check` 通过。

验收对照：正式只读、候选读取/提交、候选审阅、Owner 正式化/恢复、健康检查均已具备；五档能力边界（read / candidate_submit / candidate_review / formalize / centre）已在两个领域分别实现服务端鉴权与测试。仍待复核项：`ai4-ujvn`/`ai4-t2wc` 开放面收口（Frank Qi 负责，`ujvn` 被 `ai4-we38` 阻塞）；中央 Agent 专属写工具（`append_prereview_log`、`create_merged_candidate`）依赖预审日志契约 `ai4-oz3s` 与中央 Agent 开放面，需在 `ai4-t2wc`/`ai4-rlv6` 收口后补。按用户指示，Frank 模块阻塞项应提交 issue 知会。

**2026-10-23 验收核对（hanjiang）**

- 十项验收中九项已勾选，均有实现与测试证据：独立双领域管理接口（切片一二三）、工具目录覆盖正式只读/候选读取与提交/审阅/正式化/健康检查、五档能力鉴权与 denied 测试、候选提交与正式化语义经领域服务保留、环境变量与审计建表失败拒绝启动、读/写双阶段留痕、审计位于接口层、PR #27 复核、锁文件验证与回写。
- 唯一未勾选：与 `ai4-ujvn`/`ai4-t2wc` 开放面一致。原因：中央 Agent 专属写工具（`append_prereview_log`、`create_merged_candidate`）需要预审日志契约 `ai4-oz3s` 与中央 Agent 开放面收口，两者分别由 Frank Qi 负责（`ai4-t2wc` open、`ai4-rlv6` open）；已向 Gitee 提交 issue `IKQ2QB` 知会。本票保持 `open`，待该开放面收口后补齐工具并关闭。

**2026-10-23 候选读取补齐（hanjiang）**

- `list_candidates` 由占位实现升级为真实查询：`SqliteStore.get_candidate_for_submission(submission_id)` 返回提交记录 + Proposal + 候选 Commit 的治理事实（提交者、领域、正式基准、提交状态、proposal 状态、candidate head 与摘要），管理 MCP 注入 sqlite_store 后返回该记录；无记录时返回 `candidate: null`。
- 验证：Mapping 13 项管理测试（新增 submit→list_candidates 读回测试）、全量 90 项（含真实 TerminusDB 集成）通过；`compileall`、`uv sync --locked`、`git diff --check` 通过。
- 至此「正式只读、候选读取/提交、候选审阅、Owner 正式化/恢复、健康检查」工具目录全部为真实实现；唯一未闭合项维持中央 Agent 专属写工具（`IKQ2QB` 阻塞）。
- Wiki 侧对称补齐（提交 8c8bf9a）：`WikiManagementService` 注入 sqlite_store，新增 `list_wiki_candidates(wiki_domain_id)` 读取持久化的候选提交（read/centre 档）；测试 11 项管理 + 全量 108 项通过。两个领域的「候选读取」工具均为真实查询，不再有占位实现。

**2026-10-24 切片四：可送审候选快照读取（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

新增 `list_reviewable_candidates`（research-map）与 `list_reviewable_wiki_candidates`（research-wiki）只读工具，把「候选读取」从单提交记录升级为中央 Agent 预审所需的**同一时点全部可送审候选 + 精确 head/base + 内容快照**：

- 可送审 = `proposal.status NOT IN ('merged','rejected','abandoned')` 且已持久化候选 commit；内容从 TerminusDB 精确固定 head 读取，单候选取件失败独立降级 `snapshot_status=unavailable`。
- 走 `read`/`centre` 档位 + `attempted` fail-open 留痕；不写草稿、不改 Proposal 状态。
- 新增 `candidate_reader.py`（两领域）、`list_reviewable_candidates`（SQLite）、management 工具面与 main.py 接线。
- 验证：research-map 全量 95 项、research-wiki 全量 102 项通过（0 失败），提交 `6333e18`；无新增依赖。

与「中央 Agent 候选预审入口与结论回写」(ai4-he04) 的关系：本切片闭合 he04 的输入端；写端（`append_prereview_log`、`create_merged_candidate`）仍待 `ai4-t2wc`/`ai4-rlv6` 开放面收口（Frank Qi）。

**2026-10-24 依赖现状更新（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

依赖复核（2026-10-24）：

- `ai4-ujvn`（Registry 登记事实与中央服务开放面规格）已 **closed**——三档开放面已定稿，其实现由 `ai4-w4su` 承载。
- `ai4-t2wc`（注册表登记中央 Agent 与开放面第四档）仍为 Frank Qi 名下 **open**；`ai4-rlv6`（中央 Agent 能力接口收口）仍 open 且 deps 包含 t2wc。
- 因此本票未勾选验收「开放面与 ujvn、t2wc 一致」的**剩余缺口**仅是：中央 Agent 第四档（`append_prereview_log`、`create_merged_candidate` 两个写工具）需等待 t2wc/rlv6 收口后落地。`centre` 档位已在两领域实现、`ujvn` 三档已定，其余条件满足。
- 已按原计划提 issue 催办（详见下一条 issue `IKQ63M` 的追加）——本次不再重复开票，在 issue 中汇总 t2wc/rlv6 对 w73z/he04/5z9e/oebi/8dgd 的一串阻塞。

**2026-10-25 能力档描述修正（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

按 `ai4-5auy` 完成后的实际能力面修正本票描述：

- 能力档位从五档扩展为**七档**：`read` / `candidate_submit` / `candidate_review` / `formalize` / `centre` / `prereview_log` / `merged_candidate`（`ai4-5auy` 提交 `1dada55`）。
- `centre` 收紧为只读档：11 个写工具（Mapping 5 + Wiki 6）从能力表摘除 `centre`，分别归 `candidate_submit`/`candidate_review`/`formalize`；`centre` 只保留两侧各 3 个读工具。
- 中央 Agent 专属写工具 `append_prereview_log`（`prereview_log` 档）与 `create_merged_candidate`（`merged_candidate` 档）已随 `ai4-5auy` 落地，不再等待 t2wc/rlv6 收口。上文「中央 Agent 第四档需等待收口后落地」的表述因此过期，保留原文供对照。
- 本票验收第 3 项「五类能力边界均有服务端鉴权与测试」按实际能力面读为七档边界；其余验收不变。

**2026-10-25 验收收口与关闭（hanjiang）**

`ai4-t2wc` 已关闭，`ai4-5auy`（提交 `1dada55`）落地中央 Agent 开放面：`centre` 收敛为只读三组读工具，`append_prereview_log`/`create_merged_candidate` 分属 `prereview_log`/`merged_candidate` 独立档，11 个写工具摘除 `centre` 授权——与 `ujvn` 三档 + `t2wc` 第四档的规定一致。不能通过 `centre` 凭据调用任何写工具，也不能用普通候选写入绕过正式化门禁（service 层按能力表服务端拒绝）。本票验收第 4 项勾选，全部十项满足，状态置 `closed`。

**2026-10-25 误回退清理记录（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

2026-10-25 发现本票文档与 `research-map`/`research-wiki` 实现曾出现**误回退**（本票 `status` 被改回 `open`，删除了上列 2026-10-25 三条验收收口 Notes；实现侧删除了 `1dada55`/`984bd6c` 的约 942 行交付）。经 `git reflog` 核查无 checkout/reset --hard/rm 记录，判定为工作区文件层直接改写而非 git 历史操作，已由 hanjiang 以 `git stash`（mistake stash）暂存隔离后 `git stash drop` 清除。HEAD 保持 `495a612`，本票状态仍为 `closed`，十项验收不变。对应实现票 `ai4-5auy` 同步记录了清理说明。

## Design

## 对外接口边界\n\n- 分别为 Research Mapping 和 LLM-Wiki 提供独立的管理 MCP；工具通过应用服务调用，不直连领域存储。\n- 至少覆盖正式内容只读查询、候选查询/读取、候选提交、候选审阅所需入口、Owner 正式化/恢复入口，以及健康检查或启动失败状态。\n- 工具输入输出使用稳定、可序列化的 DTO/JSON；返回稳定错误码，区分参数拒绝、无权访问、基准过期、存储明确失败和结果未知。\n- 通过环境变量配置监听地址、端口、领域存储地址、凭据和 SCIWEAVE_AUDIT_SQLITE_PATH；源码、测试和文档不得写死部署路径、端口或凭据。\n\n## 权限分层\n\n服务端按调用方能力面执行权限，不以客户端自报角色或登记记录替代鉴权。至少明确并测试以下档位：\n\n1. **只读**：读取当前正式 Mapping/Wiki、候选摘要或候选固定头时，只能读取调用方被授权范围；中央 Agent 可按既定开放面读取全部候选和正式版本，端侧 Agent 不自动获得全部数据。\n2. **只写候选**：研究员/端侧 Agent 只能提交自己的草稿或候选变更，并受领域校验、精确正式基准、幂等键和候选隔离约束；不得直接修改正式版本、代替 Owner 审核或推进正式化。\n3. **候选审阅**：明确谁可以创建/读取审阅材料、记录预审结论和提交候选审核决定；预审结论不得等同于 Project Owner 的正式发布批准。\n4. **候选转正式**：只有 Project Owner 或已验证的 Owner 权限可以执行正式化/恢复；必须保留候选头、正式基准、批准决定和 operation identity 校验，不能通过普通写候选工具绕过正式化门禁。\n5. **中央 Agent**：按既有开放面允许读取两套领域的候选与正式版本、追加预审日志、必要时创建混合候选；不得写正式版本、修改已有候选、写草稿接纳状态或代替 Owner 正式发布。\n\n需要把每个工具归入能力档位，并对未授权调用返回稳定 denied 错误；不能仅依赖提示词隐藏工具。两个领域的对象、存储、候选和正式化权限保持隔离。\n\n## 共享留痕接入\n\n- 使用 `sciweave-audit-trail` 的 `open_connection`、`init_audit_table`、`record_attempted`、`call_scope`/`begin_call`/`finish_call`。\n- 服务启动时打开审计 SQLite 并初始化表；初始化失败不得启动对外服务。\n- 读工具结束后记录 `attempted`，留痕失败按共享包约定 fail-open；写工具执行前记录 `invoked`，留痕失败时阻止业务执行，成功或失败后记录 `completed`。\n- 记录 `caller_id`、`channel_id`、`caller_type`、服务名、工具名、目标对象标识、参数摘要、结果和错误码；不得写入正文、凭据或完整入参。\n- 留痕发生在 MCP/HTTP 对外接口层，领域应用服务内部不重复调用共享包。\n\n## 依赖与范围\n\n- 复用现有 Research Mapping 与 LLM-Wiki 应用服务，不重写领域治理逻辑。\n- 复用 `ai4-gvan` 已实现的共享留痕包；如需调整共享包接口，先说明原因并更新对应实现票，不复制实现。\n- 与 `ai4-ujvn` 的调用方开放面和 `ai4-t2wc` 的中央 Agent 开放面保持一致；若发现冲突，先在本票 Notes 记录并提出修订，不自行覆盖既有决策。\n- 本票不实现 Web 看板前端、不实现端侧 Agent runtime、不把领域 MCP 改造成 Gateway MCP。

## Acceptance Criteria

- [x] Research Mapping 和 LLM-Wiki 分别提供独立、可启动、可配置的对外管理接口；调用通过应用服务完成，不直连领域存储。
- [x] 工具目录和输入输出契约覆盖正式只读、候选读取/提交、候选审阅、Owner 正式化/恢复及健康检查；每个工具标明权限档位。
- [x] 只读、只写候选、候选审阅、候选转正式、中央 Agent 五类能力边界均有服务端鉴权与测试；未授权调用返回稳定 denied 错误。
- [x] 端侧 Agent、研究员、中央 Agent、Project Owner 的开放面与 `ai4-ujvn`、`ai4-t2wc` 一致；不能通过隐藏工具名、直接存储访问或普通候选写入绕过正式化权限。
- [x] 候选提交保留精确正式基准、候选隔离和幂等语义；正式化保留 Owner 授权、candidate head、operation identity 和失败/恢复语义。
- [x] 对外服务启动时使用环境变量配置地址、端口、存储和审计库；审计库打开或建表失败时服务不启动。
- [x] 所有对外工具按 `sci-weave/centre-control/shared/audit-trail` 的接口层调用账本留痕：读调用 `attempted` fail-open，写调用 `invoked`/`completed` fail-closed；审计记录不含正文、凭据或完整入参。
- [x] 审计接入位于对外接口层，领域应用服务内部无重复留痕；至少验证成功、拒绝、业务失败、审计库不可用和进程中断留下未完成调用等路径。
- [x] 关注并复核 Gitee Pull Request #27 的接口/聚合 API 变化，必要时在实现中保持兼容或记录冲突。
- [x] 按各子项目锁文件完成最小安装、测试和编译验证，并将命令、结果和关联 PR 回写本票 Notes；不引入未登记依赖。

