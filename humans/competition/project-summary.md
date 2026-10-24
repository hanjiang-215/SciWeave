# SciWeave：科研协作与可审计智能体平台——项目说明（≤5 页）

> 状态：说明材料草稿（2026-10-23）。验证结果与 SciencePal 实演证据待补后回填；本文件不超过 5 页，随作品提交前复核。

## 1. 技术方案

SciWeave 是一个面向科研团队的协作与智能体平台，把「科研路线 → 任务执行 → 结果接纳 → 路线变更提案 → 正式发布」沉淀为可追溯、可审计的闭环。平台核心保持学科中立，用一个可替换的示例场景（UCI Iris 分类复现）验证通用能力。

架构分三层：

- **Research Mapping（科研地图）**：版本化 TaskNode 与 Dependency Edge 表达研究路线；正式版本、候选变更与草稿视图分离。数据模型和治理记录分别落在 TerminusDB（不可变图快照）与 SQLite（治理索引），按精确 Commit 读取，不允许回退到"最新版本"。
- **LLM-Wiki（知识库）**：WikiDocument 与 ResourceVersion 的引用资格审核、候选 Proposal 与正式 WikiRevision 生命周期，与 Research Mapping 共用治理语义但保持独立 MCP、存储与审计边界。
- **Work Agent（执行）**：Task Agent（研究员端侧）与 Centre Agent（中央）统一架构——消息驱动触发、短生命周期 Worker 执行一轮 fast-agent loop、ExecutionRecord 为唯一状态机、结果写入中央草稿箱后由人一审。

对外接口是两套独立的领域管理 MCP（Mapping 7 工具 / Wiki 8 工具），覆盖正式只读、候选提交、候选审阅、Owner 正式化/恢复与健康检查；服务端按五档能力（read / candidate_submit / candidate_review / formalize / centre）鉴权，Bearer 令牌注入调用者身份，不信任客户端自报角色；所有工具调用写入接口层审计账本（读 attempted fail-open，写 invoked/completed fail-closed）。

## 2. 创新点

1. **学科中立 + 可替换场景**：平台核心不含任何学科对象；演示场景只是可替换的验证夹具（UCI Iris → NOAA CO₂ 可无缝替换），保证通用科研协作流程不被学科绑定。
2. **精确 Commit 的不可变治理**：正式内容只按 `store/database/branch/commit` 精确读取，候选隔离分支、Owner 批准后原子激活、失败恢复对账，杜绝"用最新版本冒充正式版本"。
3. **消息驱动 + MCP 只做人工介入**：任务下发只走消息队列；Gateway MCP 只承担返修、处置、回答提问与观察；领域 MCP 是 Agent 的工具箱。通道分工避免"MCP 既是下发又是介入"的权限混淆。
4. **接口层统一留痕**：读调用 attempt 记录 fail-open、写调用 invoked/completed fail-closed，审计位于对外接口层、领域服务不重复接入，可回答"谁在什么时候调用了什么工具"。
5. **单 Worker 多 Agent**：一个平台级 Work Agent 对应一个 Worker、一个 ExecutionRecord、一个最终 draft_id；Router/Orchestrator/Parallel/Agents-as-Tools 四类工作流在 Worker 内协作，状态可审计。

## 3. 验证结果

| 模块 | 证据 |
| --- | --- |
| Research Mapping 持久化与正式化 | 90 项测试（5 跳过） + 真实 TerminusDB 12.0.8 集成（候选隔离、正式化、精确读回、失败恢复） |
| LLM-Wiki 候选与资格审核 | 96 项测试（4 跳过） + 真实 TerminusDB 集成（引用精确绑定、资格门槛、Owner 正式化、撤回阻断） |
| 中央草稿箱 | 25 项测试（1 跳过，含真实 TerminusDB 临时库集成），幂等、固定提交、命名空间隔离 |
| 领域管理 MCP 与权限分层 | Mapping 13 + Wiki 11 项管理测试，全量 Mapping 90 / Wiki 96 项通过（2026-10-24 本机实测） |
| 看板只读聚合 API | 17 项测试（2026-10-24 实测），来源降级 unavailable/partial、不泄露凭据/堆栈 |
| Web 看板前端 | 26 项测试通过、Vite 构建通过（2026-10-24 实测） |
| 研究员套件 runtime | 18 项测试通过（含标准 MCP 卡片加载验证，2026-10-24 实测） |
| 演示证据链 | T1 输入检查通过（150 行、哈希匹配、3 类各 50）；T2 确定性 KNN 基线本机可复现（准确率 0.955556，混淆矩阵完整）；真实平台治理链路（TerminusDB + 管理 MCP）完整跑通并产出 `iris_platform_pipeline.json` |

## 4. 当前局限

- SciencePal 实演尚未接入：赛事硬门槛要求 SciencePal 实际承接核心数据检查或分析执行；本机 T1/T2 脚本只证明闭环可复现，不替代 SciencePal 执行记录。
- 中央 Agent 专属写工具（预审日志追加、混合候选新建）依赖注册表开放面收口，尚未对外暴露。
- 看板 Gateway 与消息监听来源依赖 Gateway 侧只读契约，当前以 unavailable/partial 降级展示。
- 单机验证为主；跨进程、跨机部署与生产级恢复仍待后续阶段。

## 5. 后续计划

1. SciencePal 接入演示闭环，回填真实执行记录与工具版本；
2. 完成中央 Agent 开放面收口与预审工具；
3. 补看板 Gateway 来源真实数据；
4. 录制 3–5 分钟演示视频并完成 5 页说明定稿；
5. 打包可复现证据（数据快照、脚本、结果），核对原创性与资源声明后提交。

---

## 附件 A：原创性与资源使用声明（草稿）

| 类别 | 说明 |
| --- | --- |
| 模型 | 演示 T2 基线使用固定参数 KNN（标准库实现），未引入外部模型；fast-agent 运行时用于 Work Agent 执行，未使用需单独授权的模型凭据 |
| 数据 | UCI Iris（CC BY 4.0，DOI `10.24432/C56C76`，须署名）；NOAA CO₂ 仅作替换验证设计，未打包再分发 |
| 代码 | 全部为本项目赛期开发；无赛前既有产品代码复用 |
| API/外部工具 | 本机 TerminusDB 12.0.8（Docker 本地验证服务，非生产依赖）；Gitee（协作）；Docker（本地容器） |
| 团队分工 | 由 hanjiang 与 Frank Qi 在 `feature/*` 分支分别推进；本文件作者为 hanjiang |
| 合规 | 仓库不提交真实凭据、`.env`、构建产物；数据集使用遵守各自许可并保留署名 |

> 待 SciencePal 实际运行后，补充其工作流链接、执行记录与外部模型/API 使用清单。