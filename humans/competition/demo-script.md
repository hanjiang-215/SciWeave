# 3–5 分钟可复现演示脚本（草稿）

> 状态：脚本草稿（2026-10-23），2026-10-24 补充平台治理链路实演，2026-10-27 在合并 `develop` 后的 HEAD 上复跑、回填实测耗时，并按计时核对把估算从 310s 压到 260s。输入快照、T1 检查、T2 基线、失败注入与真实治理链路均已在当前 HEAD 上跑通（见 `demo-evidence/`），仅 SciencePal 实演记录与口播实测待回填。

## 前置（SciencePal 接入后）

- SciencePal 项目/工作流链接：待回填
- 固定 T1/T2 脚本与参数（`check_iris_input.py`、`run_iris_baseline.py`）
- **一键执行入口已就绪**：`demo-evidence/sciencepal-runs/run_t1_t2_on_sciencepal.py`（含 README）把两个脚本 + 锁定数据快照交给 SciencePal 沙箱执行、下载产物、核对后落盘 `sciencepal_t1_t2_evidence.json`；已用假 SciencePal 服务本地验证全流程，平台网络恢复即可实跑
- 真实平台治理链路已可独立实演（不依赖 SciencePal）：`run_iris_mapping_pipeline.py`，前置为本机 TerminusDB 已启动、凭据经环境变量提供
- 准备好 2 个窗口：SciencePal、终端（终端里同时展示治理链路输出与 TerminusDB 查询结果）

**不使用 Web 看板**（自 `ai4-vyuw` 起）：看板在 `apiUrl` 为空时走 fixture 查询（`sci-weave/centre-control/web-ui/src/App.vue:15`），页面会显示「演示数据模式 / 不代表真实服务状态」的橙色横幅，且 `dashboard-api` 的队列数据来源尚无实现。段 6 的审计追溯改用 TerminusDB 界面或接口层审计账本，两者都是真实数据。这条路不花实现成本，只是不再依赖一个当天可能露馅的窗口。

**不需要公网 MCP 端点**：SciencePal 段（第 2–4 段）只运行两个纯标准库脚本，既不调中央 MCP，也不走 path A / path B 的任何一条。`sciencpal-onboarding/docs/deploy-central-mcp.md` 的公网隧道方案是 `ai4-v869` 的对接预案（SciencePal 若要真正调用中央管理 MCP，无论配原生 MCP 还是封装 skill，都必须先有可达端点），与**本场演示**无关，可整段跳过。这条结论不改变 v869 的预案口径，只划清演示范围与后续对接范围。

## 脚本正文

### 1. 开场：提出科研痛点（约 25 秒）

> 口播要点：科研团队协作的最大成本不在计算，而在「谁改了路线、为什么改、改完有没有被正式采纳」。SciWeave 把科研路线做成了可版本、可审计的图，任何人执行、审核、变更都有迹可循。今天用一份经典 Iris 数据演示这个闭环。

**演示动作**：打开 Research Mapping 初始路线 `T1 → T2 → T3`，指出每个节点的 Owner 与依赖。

### 2. T1 固定并检查输入（约 40 秒）

**演示动作**：SciencePal 执行 `check_iris_input.py`，展示数据检查记录。

> 口播要点：T1 不是"读文件就成功"。它核验来源、DOI、快照 SHA-256、150 行、4 个特征列、3 类各 50 条、无缺失值。任何一项不符就留下 Execution Record 失败，不产生分析结果。

**预期演示**：检查通过，输出 `status: ok` 的 JSON 记录，快照哈希与卡片一致。

### 3. T2 执行基线分类（约 45 秒）

**演示动作**：SciencePal 执行 `run_iris_baseline.py`，展示指标与混淆矩阵。

> 口播要点：T2 是预先固定的确定性 KNN 基线——K=3、种子固定、分层划分 70/30。准确率 0.955556，45 条测试样本，混淆矩阵完整。结果是可复现的，不是运气。

**预期演示**：准确率与混淆矩阵可见，输出记录 `iris_baseline_result.json`。

### 4. 失败注入 + 普通重试（约 50 秒）

**演示动作**：上传移除目标列的临时副本，T1 检查失败；恢复官方快照后重试成功。

> 口播要点：这里注入一次可观察的失败——缺列被 T1 拦截。失败只留 Execution Record，不产出结果。恢复正确输入后普通重试成功，这种"数据恢复"不改变路线，所以不需要 Proposal。

**预期演示**：失败原因清晰（如 `missing_columns`），恢复后成功。

### 5. 平台治理链路实演：候选 → 审阅 → 正式化（约 100 秒，不依赖 SciencePal）

**演示动作**：运行 `run_iris_mapping_pipeline.py`（真实 TerminusDB + 真实管理 MCP），按逗号分隔的时序把六类 MCP 调用逐个展示：

1. `get_formal_mapping` 读取初始正式路线；
2. `submit_candidate` 提交加入 T4 分层交叉验证的路线变更候选（`status: confirmed`，候选 Commit 落真实 TerminusDB）；
3. `preview_candidate` 生成 Diff 与影响预览；
4. `record_review` 先驳回一次（`rejected`，正式图不变），再批准（`approved`）；
5. `formalize_candidate` 生成新的 Formal MappingRevision（`status: succeeded`）；
6. `get_formal_mapping` 确认 T4 已进入正式图，`list_candidates` 读回候选治理记录。

同时展示三条失败路径的稳定错误：无 `candidate_submit` 权限返回 `forbidden`、不存在的正式基准在提交时即被拒绝并返回 `base_revision_missing`、驳回后正式图不含被驳回节点。

> 口播要点：候选不是直接改正式图。它先在隔离分支上产生不可变 Commit，经差异预览和两层审核（TaskNode Owner 接纳结果、Project Owner 批准路线）后才正式化；正式化只是一次原子 SQLite 激活，把指针切到已锁定的 Commit。每次 MCP 调用都写接口层审计账本，失败路径各自留下稳定错误码。

**预期演示**：终端按序打印每步 JSON，最终正式图中出现 T4；`iris_platform_pipeline.json` 保留完整时间线供评审追溯。

### 6. 审计追溯 + 收尾（并入段 5，不单独计时）

**演示动作**：段 5 的终端不要关，直接在同一块屏上展示接口层审计账本或治理记录中的关键事件（提交、接纳、批准、正式化）。两个窗口全程只用 SciencePal 与终端，切屏次数从 3 次降到 1 次。

> 口播要点：每一步调用都留痕，谁在什么时候提交、接纳、批准、正式化，都能查回。这就是可复现、可审计的科研协作。

## 计时核对

**本机实测的脚本执行时间**（2026-10-27，`feature/frank-qi`，三次取稳定值）：

| 脚本 | 执行时间 |
| --- | --- |
| `check_iris_input.py iris_data.csv` | 0.02s |
| `run_iris_baseline.py iris_data.csv` | 0.02s |
| `run_iris_mapping_pipeline.py`（真实 TerminusDB） | 1.1s |

三个脚本都在 1 秒量级，**各段时长因此几乎完全由讲解与操作决定，不由计算决定**——每一秒的超支都只能靠砍讲解回收。

### 初版估算：310s，超上限

| 段 | 初版预计 |
| --- | --- |
| 1 开场 | 40s |
| 2 T1 检查 | 40s |
| 3 T2 基线 | 60s |
| 4 失败+重试 | 50s |
| 5 平台治理链路 | 90s |
| 6 审计收尾 | 30s |
| **合计** | **310s（≈5:10）** |

### 已采纳的压缩方案：260s，落在 3–5 分钟内

310s 比 5 分钟多 10s，且没有任何缓冲。按「脚本耗时可以忽略、讲解耗时才是变量」的判断，砍掉三处冗余讲解：

| 段 | 初版 | 压缩后 | 怎么砍的 |
| --- | --- | --- | --- |
| 1 开场 | 40s | 25s | 只留「谁改了路线、为什么改」这一句钩子，删掉赛道背景铺垫 |
| 2 T1 检查 | 40s | 40s | 不动。失败注入的对照组，讲清楚判据 |
| 3 T2 基线 | 60s | 45s | 只讲「K=3、种子固定、0.955556」三点，混淆矩阵不逐格念 |
| 4 失败+重试 | 50s | 50s | 不动。「故障恢复 vs 路线变更」的关键区分 |
| 5 平台治理链路 | 90s | 100s | 不砍反而加时：这是平台本身的可演示核心，六步值得讲透 |
| 6 审计收尾 | 30s | 0s | 并入段 5 的尾部，用同一块屏（TerminusDB 审计视图）连讲 |
| **合计** | **310s** | **260s（≈4:20）** | 省 50s，留 40s 缓冲 |

**为什么砍这三处、不砍另外两处**：段 1 的铺垫可以在书面材料里读，段 3 的混淆矩阵在 `iris_baseline_result.json` 里可查，段 6 与段 5 本来就在同一块屏上——这三处省下来观众不会丢失信息。段 2、段 4 是失败注入与恢复的完整对照，段 5 是被演示的系统本身，砍掉就等于不演示核心。

表内时长为**估算**。真实口播节奏需在录制时掐表回填；若实测仍超 5 分钟，第一顺位继续压段 3 到 30s，第二顺位把段 1 压到 15s。

## 本机实测记录（2026-10-24，2026-10-27 在合并后 HEAD 复跑）

- 平台治理链路脚本在真实 TerminusDB（本机 `127.0.0.1:6363`，凭据经环境变量提供）上完整跑通，退出码 0；完整 MCP 请求/响应时间线见 `demo-evidence/iris_platform_pipeline.json`。
- 该链路同时经真实 HTTP 管理 MCP 验证了 `tools/list` 暴露的工具面与套件标准卡片一致（`ai4-emfn`），并触发修复了共享留痕包的多线程访问缺陷（`ai4-fmco`）。
- **2026-10-27 复跑**：`develop` 合入 `feature/frank-qi`（合并提交 `e54aa92`）后重新执行，退出码 0、耗时 1.1s，六步时序完整，三条失败路径均返回预期错误码（`forbidden` / `base_revision_missing` / `rejected`），`formal_mapping_contains_t4: true`。证据文件已重新生成并转为 UTF-8。
- SciencePal 段（2、3）的实际计时与执行记录仍待回填。
