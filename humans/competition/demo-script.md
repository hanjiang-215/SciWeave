# 3–5 分钟可复现演示脚本（草稿）

> 状态：脚本草稿（2026-10-23），2026-10-24 补充平台治理链路实演。实际计时与录制需在 SciencePal 接入后复核；各段预计时长以 `[秒]` 标注，合计目标 3–5 分钟。输入快照、T1 检查、T2 基线与本机真实治理链路均已跑通（见 `demo-evidence/`），SciencePal 实演后回填真实执行记录。

## 前置（SciencePal 接入后）

- SciencePal 项目/工作流链接：待回填
- 固定 T1/T2 脚本与参数（`check_iris_input.py`、`run_iris_baseline.py`）
- 真实平台治理链路已可独立实演（不依赖 SciencePal）：`run_iris_mapping_pipeline.py`
- 准备好 3 个浏览器/窗口：Web 看板或任务面板、SciencePal、TerminusDB 或审计视图

## 脚本正文

### 1. 开场：提出科研痛点（约 40 秒）

> 口播要点：科研团队协作的最大成本不在计算，而在「谁改了路线、为什么改、改完有没有被正式采纳」。SciWeave 把科研路线做成了可版本、可审计的图，任何人执行、审核、变更都有迹可循。今天用一份经典 Iris 数据演示这个闭环。

**演示动作**：打开 Research Mapping 初始路线 `T1 → T2 → T3`，指出每个节点的 Owner 与依赖。

### 2. T1 固定并检查输入（约 40 秒）

**演示动作**：SciencePal 执行 `check_iris_input.py`，展示数据检查记录。

> 口播要点：T1 不是"读文件就成功"。它核验来源、DOI、快照 SHA-256、150 行、4 个特征列、3 类各 50 条、无缺失值。任何一项不符就留下 Execution Record 失败，不产生分析结果。

**预期演示**：检查通过，输出 `status: ok` 的 JSON 记录，快照哈希与卡片一致。

### 3. T2 执行基线分类（约 60 秒）

**演示动作**：SciencePal 执行 `run_iris_baseline.py`，展示指标与混淆矩阵。

> 口播要点：T2 是预先固定的确定性 KNN 基线——K=3、种子固定、分层划分 70/30。准确率 0.955556，45 条测试样本，混淆矩阵完整。结果是可复现的，不是运气。

**预期演示**：准确率与混淆矩阵可见，输出记录 `iris_baseline_result.json`。

### 4. 失败注入 + 普通重试（约 50 秒）

**演示动作**：上传移除目标列的临时副本，T1 检查失败；恢复官方快照后重试成功。

> 口播要点：这里注入一次可观察的失败——缺列被 T1 拦截。失败只留 Execution Record，不产出结果。恢复正确输入后普通重试成功，这种"数据恢复"不改变路线，所以不需要 Proposal。

**预期演示**：失败原因清晰（如 `missing_columns`），恢复后成功。

### 5. 平台治理链路实演：候选 → 审阅 → 正式化（约 90 秒，不依赖 SciencePal）

**演示动作**：运行 `run_iris_mapping_pipeline.py`（真实 TerminusDB + 真实管理 MCP），按逗号分隔的时序把六类 MCP 调用逐个展示：

1. `get_formal_mapping` 读取初始正式路线；
2. `submit_candidate` 提交加入 T4 分层交叉验证的路线变更候选（`status: confirmed`，候选 Commit 落真实 TerminusDB）；
3. `preview_candidate` 生成 Diff 与影响预览；
4. `record_review` 先驳回一次（`rejected`，正式图不变），再批准（`approved`）；
5. `formalize_candidate` 生成新的 Formal MappingRevision（`status: succeeded`）；
6. `get_formal_mapping` 确认 T4 已进入正式图，`list_candidates` 读回候选治理记录。

同时展示三条失败路径的稳定错误：无 `candidate_submit` 权限返回 `forbidden`、过期基准返回 `stale_base`、驳回后正式图不含被驳回节点。

> 口播要点：候选不是直接改正式图。它先在隔离分支上产生不可变 Commit，经差异预览和两层审核（TaskNode Owner 接纳结果、Project Owner 批准路线）后才正式化；正式化只是一次原子 SQLite 激活，把指针切到已锁定的 Commit。每次 MCP 调用都写接口层审计账本，失败路径各自留下稳定错误码。

**预期演示**：终端按序打印每步 JSON，最终正式图中出现 T4；`iris_platform_pipeline.json` 保留完整时间线供评审追溯。

### 6. 审计追溯 + 收尾（约 30 秒）

**演示动作**：展示接口层审计账本或治理记录中的关键事件（提交、接纳、批准、正式化）。

> 口播要点：每一步调用都留痕，谁在什么时候提交、接纳、批准、正式化，都能查回。这就是可复现、可审计的科研协作。

## 计时核对

| 段 | 预计 | 实际（待 SciencePal 后填） |
| --- | --- | --- |
| 1 开场 | 40s | |
| 2 T1 检查 | 40s | |
| 3 T2 基线 | 60s | |
| 4 失败+重试 | 50s | |
| 5 平台治理链路 | 90s | |
| 6 审计收尾 | 30s | |
| 合计 | 310s（≈5:10，预留压缩空间） | |

> 若超时，优先压缩段 3 的讲解；段 4 的失败注入与段 5 的平台链路保留，前者是"故障恢复 vs 路线变更"的关键区分，后者是平台本身的可演示核心。段 5 已有本机实测运行时间基线（真实 TerminusDB 内容约数十秒，见 `run_iris_mapping_pipeline.py` 输出）。

## 本机实测记录（2026-10-24）

- 平台治理链路脚本在真实 TerminusDB（本机 `127.0.0.1:6363`，凭据经环境变量提供）上完整跑通，退出码 0；完整 MCP 请求/响应时间线见 `demo-evidence/iris_platform_pipeline.json`。
- 该链路同时经真实 HTTP 管理 MCP 验证了 `tools/list` 暴露的工具面与套件标准卡片一致（`ai4-emfn`），并触发修复了共享留痕包的多线程访问缺陷（`ai4-fmco`）。
- SciencePal 段（2、3）的实际计时与执行记录仍待回填；回填后本表的"实际"列更新并复核总时长。