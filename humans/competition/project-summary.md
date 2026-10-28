# SciWeave：科研协作与可审计智能体平台——项目说明（≤5 页）

> 状态：说明材料（2026-10-27 更新）。验证结果表已回填今晚全流程实测（21/21 阶段、872 项测试）；唯一未闭合项是 SciencePal 实际承载执行（执行包已就绪，网络恢复即可跑），见第 4 节。

## 1. 技术方案

SciWeave 是一个面向科研团队的协作与智能体平台，把「科研路线 → 任务执行 → 结果接纳 → 路线变更提案 → 正式发布」沉淀为可追溯、可审计的闭环。平台核心保持学科中立，用一个可替换的示例场景（UCI Iris 分类复现）验证通用能力。

架构分三层：

- **Research Mapping（科研地图）**：版本化 TaskNode 与 Dependency Edge 表达研究路线；正式版本、候选变更与草稿视图分离。数据模型和治理记录分别落在 TerminusDB（不可变图快照）与 SQLite（治理索引），按精确 Commit 读取，不允许回退到"最新版本"。
- **LLM-Wiki（知识库）**：WikiDocument 与 ResourceVersion 的引用资格审核、候选 Proposal 与正式 WikiRevision 生命周期，与 Research Mapping 共用治理语义但保持独立 MCP、存储与审计边界。
- **Work Agent（执行）**：Task Agent（研究员端侧）与 Centre Agent（中央）统一架构——消息驱动触发、短生命周期 Worker 执行一轮 fast-agent loop、ExecutionRecord 为唯一状态机、结果写入中央草稿箱后由人一审。

对外接口是两套独立的领域管理 MCP（Mapping 11 工具 / Wiki 11 工具，2026-10-27 按两处 `TOOL_DEFINITIONS` 逐条计数），覆盖正式只读、候选提交、候选审阅、Owner 正式化/恢复与健康检查；服务端按五档能力（read / candidate_submit / candidate_review / formalize / centre）鉴权，Bearer 令牌注入调用者身份，不信任客户端自报角色；所有工具调用写入接口层审计账本（读 attempted fail-open，写 invoked/completed fail-closed）。

## 2. 创新点

1. **学科中立 + 可替换场景**：平台核心不含任何学科对象；演示场景只是可替换的验证夹具（UCI Iris → NOAA CO₂ 可无缝替换），保证通用科研协作流程不被学科绑定。
2. **精确 Commit 的不可变治理**：正式内容只按 `store/database/branch/commit` 精确读取，候选隔离分支、Owner 批准后原子激活、失败恢复对账，杜绝"用最新版本冒充正式版本"。
3. **消息驱动 + MCP 只做人工介入**：任务下发只走消息队列；Gateway MCP 只承担返修、处置、回答提问与观察；领域 MCP 是 Agent 的工具箱。通道分工避免"MCP 既是下发又是介入"的权限混淆。
4. **接口层统一留痕**：读调用 attempt 记录 fail-open、写调用 invoked/completed fail-closed，审计位于对外接口层、领域服务不重复接入，可回答"谁在什么时候调用了什么工具"。
5. **单 Worker 多 Agent**：一个平台级 Work Agent 对应一个 Worker、一个 ExecutionRecord、一个最终 draft_id；Router/Orchestrator/Parallel/Agents-as-Tools 四类工作流在 Worker 内协作，状态可审计。

## 3. 验证结果

| 模块 | 证据 |
| --- | --- |
| Research Mapping 持久化与正式化 | 132 项测试（5 跳过，2026-10-28 合并后实测） + 真实 TerminusDB 12.0.8 集成（候选隔离、正式化、精确读回、失败恢复） |
| LLM-Wiki 候选与资格审核 | 141 项测试（12 跳过，2026-10-28 合并后实测） + 真实 TerminusDB 集成（引用精确绑定、资格门槛、Owner 正式化、撤回阻断） |
| 中央草稿箱 | 30 项测试（3 跳过，2026-10-28 合并后实测，含真实 TerminusDB 临时库集成），幂等、固定提交、命名空间隔离 |
| 领域管理 MCP 与权限分层 | Mapping 31 + Wiki 27 项管理测试，五档能力鉴权、接口层审计留痕（2026-10-27 全流程实测） |
| 邮件服务 | 114 项测试（2026-10-27 实测），真实 SMTP 发送已合入，演示凭据未配置 |
| 看板只读聚合 API | 17 项测试，来源降级 unavailable/partial、不泄露凭据/堆栈 |
| Web 看板前端 | 26 项测试通过、Vite 构建通过 |
| 研究员套件 runtime | 370 项测试通过（2026-10-28 本分支持久化 runtime 全量实测，含 MCP 按 agent 注入、多 Agent 工作流预设、无 key 端到端）；跨 harness 科学桥 35 项测试（SciencePal run 发起/轮询/产物收集/执行报告组装） |
| 中央服务部署单元 | 单镜像单容器（supervisord 12 角色进程），compose 实跑 20s 内 healthy、11 RUNNING，治理事件（mapping/wiki 候选提交与正式发布）经 Kafka 发布已接线 |
| 演示证据链 | T1 输入检查通过（150 行、哈希匹配、3 类各 50）；T2 确定性 KNN 基线本机可复现（准确率 0.955556，混淆矩阵完整）；真实平台治理链路（TerminusDB + 管理 MCP）完整跑通并产出 `iris_platform_pipeline.json` |
| 回归矩阵 | 21/21 阶段全绿、872 项 pytest 通过、22 项跳过（依赖真实 TerminusDB/Kafka 的集成用例已另行真库验证），2026-10-27 零缓存工作区首跑即绿 |

## 4. 当前局限

- SciencePal 实际承载执行仍待闭合（赛事硬门槛）：bridge 已实测可发起 run、读终态、收产物（smoke 级），T1/T2 固定参数执行包已固化在 `humans/competition/demo-evidence/sciencepal-runs/`，SciencePal 平台网络恢复即可跑出真实执行记录；目前 T1/T2 本机脚本只证明闭环可复现，不替代 SciencePal 实演。
- `ai4-grlc` 的跨平台逃逸缺陷已修并关闭：`session_dir` 的盘符/反斜杠改按文本判断，Linux 上不再复现红线（2026-10-28 实测通过）。剩余缺口是 CI 在 Gitee 上尚未真正执行，Linux 侧回归依赖人工容器复现。
- 看板映射来源随新库无正式版本显示 unavailable（正确语义），queue 来源因 subscriber 未配置真实 broker 尚未点亮。
- 公网反代与 TLS 未落地（评审期可访问链接依赖此项）；密钥管理仍为部署方 `.env` 方案。

## 5. 后续计划

1. SciencePal 平台恢复后运行固化执行包，回填真实执行记录、工具版本与工作流链接，兑现赛事硬门槛；
2. 把 Linux 容器复现纳入常规回归（`ai4-grlc` 的缺陷本身已修，待决的是 `docs/ci.md` 里的 CI 落地）；
3. 配置公网反代与 TLS，确保评审期链接可访问；
4. 录制 3–5 分钟演示视频并完成说明定稿；
5. 打包可复现证据（数据快照、脚本、结果），核对原创性与资源声明后提交。

---

## 附件 A：原创性与资源使用声明（草稿）

| 类别 | 说明 |
| --- | --- |
| 模型 | 演示 T2 基线使用固定参数 KNN（标准库实现），未引入外部模型；fast-agent 运行时用于 Work Agent 执行，未使用需单独授权的模型凭据 |
| 数据 | UCI Iris（CC BY 4.0，DOI `10.24432/C56C76`，须署名）；NOAA CO₂ 仅作替换验证设计，未打包再分发 |
| 代码 | 全部为本项目赛期开发；无赛前既有产品代码复用 |
| API/外部工具 | SciencePal 平台（2026-10-28 实跑 T1/T2：run `dc72a8e8…`/`a666fe3d…`，产物哈希见 `demo-evidence/evidence-card.md`）；本机 TerminusDB 12.0.8（Docker 本地验证服务，非生产依赖）；Gitee（协作）；Docker（本地容器） |
| 团队分工 | 由 hanjiang 与 Frank Qi 在 `feature/*` 分支分别推进；本文件作者为 hanjiang |
| 合规 | 仓库不提交真实凭据、`.env`、构建产物；数据集使用遵守各自许可并保留署名 |

> SciencePal 实际运行证据已于 2026-10-28 补齐（平台侧 run ID、沙箱 ID、执行时间与产物 sha256 记在 `demo-evidence/evidence-card.md`）；公开评审链接需平台登录态，录制时以实时操作轨迹呈现。