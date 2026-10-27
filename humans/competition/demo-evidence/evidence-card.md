# SciWeave 默认科研示例场景：最小数字证据卡

> 状态：输入快照与 T1 检查已固化；T2 确定性基线已在本机运行并留证（2026-10-27 复跑）。SciencePal 实际承载执行仍是赛事硬门槛，见下方「待 SciencePal 补的交割物」。
>
> 关联工单：`ai4-aaff`（SciWeave 默认科研示例场景与验证证据）、`ai4-483l`（T1 行尾归一化）、`ai4-j7g2`（T2 输入哈希实测）、`ai4-fe3w`（证据编码）

## 已固化的输入快照

| 项 | 值 |
| --- | --- |
| 主演示数据集 | UCI Iris（分类任务，150 条，4 个连续特征，3 类，无缺失） |
| 官方 URL | `https://archive.ics.uci.edu/static/public/53/data.csv` |
| DOI | `10.24432/C56C76` |
| 许可证 | CC BY 4.0（演示须署名并链接许可证） |
| 快照文件 | `demo-evidence/iris_data.csv`（仓库内 LF，4,464 字节；官方下载为 CRLF，4,615 字节） |
| 快照 SHA-256 | `ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4`（行尾归一化后计算，LF 与 CRLF 两种检出结果一致） |

## T1 数据检查（已运行，2026-10-27 复跑）

命令（在 `humans/competition/demo-evidence/` 下执行）：

```text
python3 check_iris_input.py iris_data.csv
```

结果：`status: ok`，150 行、4 个特征列齐全、3 类各 50 条、无缺失值、快照哈希与锁定值一致。完整 JSON 见 `demo-evidence/iris_input_check.json`。

**失败注入样本**：`demo-evidence/iris_data_failure_inject.csv` 是移除目标列的临时副本，用于演示 T1 拦截。运行同一检查脚本得到 `status: failed`、`reason_code: missing_columns`，退出码 1，不产出后续分析结果；恢复官方输入后重试成功。失败记录见 `demo-evidence/iris_input_failure.json`。这对应演示脚本第 4 段「失败注入 + 普通重试」。

T1 的判定顺序（自 `ai4-483l` 起）是**结构在前、哈希最后**。哈希若排在前面，行数、缺失值、类别计数这三类诊断都会退化成 `source_hash_mismatch`，因为它们的前提是「文件不是锁定快照」——而任何通过哈希的文件必然就是锁定快照，那几个分支就永远不可达。现在每一种结构性失败都有自己的理由码，哈希作为成功前的最后一道门，数值被改动的文件结构全对，最终仍被拦下。理由码清单见 `demo-evidence/README.md`。

## 最小数字证据卡（首版字段）

| 字段 | 值 |
| --- | --- |
| dataset_name | UCI Iris（UCI ML Repository） |
| doi | `10.24432/C56C76` |
| license | CC BY 4.0，须署名并链接许可证 |
| source_url | 见上表官方 URL |
| acquired_at | 2026-10-23 |
| input_snapshot_sha256 | `ea110d42...b6f9f4` |
| row_count / features / classes | 150 / 4 / 3 类各 50 |
| task_node_id | 由演示初始 Research Mapping 生成（T1/T2/T3...） |
| execution_record_id | 由执行侧回填 |
| card 边界 | 首版为轻量证据卡，不等同完整 `ResourceVersion` 治理 |

## T2 分析参数（本机确定性基线已运行，待 SciencePal 回填）

T2 采用固定参数的确定性 KNN 基线，本机已用纯标准库运行并产出可复现结果：

| 参数 | 值 |
| --- | --- |
| 方法 | KNN（`run_iris_baseline.py`，仅 Python 标准库） |
| 近邻数 K | 3 |
| 随机种子 | 20261023 |
| 数据划分 | 分层划分，测试占比 0.3（训练 105 / 测试 45） |
| 指标 | 准确率 0.955556（43/45）、混淆矩阵（见 `iris_baseline_result.json`） |
| 输入快照 | `ea110d42...b6f9f4`（与 T1 一致） |

命令（在 `humans/competition/demo-evidence/` 下执行）：

```text
python3 run_iris_baseline.py iris_data.csv
```

结果文件：`demo-evidence/iris_baseline_result.json`。

T2 在计算前先断言输入哈希（自 `ai4-j7g2` 起）：哈希与固定快照不符时返回 `status: failed` / `reason_code: source_hash_mismatch`、退出码 1，且**不产出准确率与混淆矩阵**；缺列返回 `missing_columns`，非数值返回 `invalid_values`，文件不可读返回 `unreadable_input`。输出里的 `input_snapshot_sha256` 是实测值而不是常量回显——测试把期望值临时改成一个假哈希后，输出仍报文件的真实哈希，因此分析结果与输入快照之间存在可核验的绑定。

**SciencePal 硬门槛不变**：以上证明演示闭环在平台外可复现，但赛事要求 SciencePal 实际承接核心数据检查或分析执行。SciencePal 接入后应封装该脚本或同参数实现，并回填真实运行环境的解释器/库版本、输出定位与执行记录；不得以本机结果冒充 SciencePal 实演。

## 平台侧真实治理链路证据（2026-10-24 首次运行，2026-10-27 在合并后 HEAD 复跑）

不依赖 SciencePal、也不依赖假存储/内存 Store 的完整真实链路：脚本 `run_iris_mapping_pipeline.py` 用**真实 TerminusDB**（本机 `127.0.0.1:6363` admin/root，临时库建库→定义 TaskNode/DependencyEdge schema→种子正式路线 T1→T2→T3），启动真实的 Research Mapping 管理 MCP（Streamable HTTP、Bearer 鉴权、接口层留痕），然后用 MCP JSON-RPC 客户端像真实 agent harness 一样驱动完整闭环：

1. `get_formal_mapping` 初始正式图可读；
2. `submit_candidate` 提交 T4 分层交叉验证路线变更 → `status: confirmed`，候选 Commit 落真实 TerminusDB；
3. `preview_candidate` 生成审阅预览（`status: available`）；
4. `record_review` 驳回一次（`decision: rejected`）→ 正式图不变；
5. `record_review` 批准（`approved`）→ `formalize_candidate` → `status: succeeded`；
6. `get_formal_mapping` 确认 T4 已进入正式图；`list_candidates` 可读回候选治理记录。

失败路径也在同一条真实链路上验证：

- 无 `candidate_submit` 权限的 reviewer 提交 → `{code: forbidden}`；
- 不存在的正式基准上的提交 → `{status: rejected, reason_code: base_revision_missing}`（自 `ai4-eex0` 起基准校验前移到写入时门禁，不存在基准在提交即拒绝，不再进入预审；`stale_base` 判定保留给「基准存在但已非当前」的场景）；
- 驳回审阅 → 审计事件保留，正式图不含被驳回节点。

运行命令（需本机 TerminusDB 已启动，凭据经环境变量提供）。bash：

```bash
export SCIWEAVE_MAPPING_TERMINUSDB_URL="http://127.0.0.1:6363"
export SCIWEAVE_MAPPING_TERMINUSDB_STORE="admin"
export SCIWEAVE_MAPPING_TERMINUSDB_USERNAME="admin"
export SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD="root"
python3 humans/competition/demo-evidence/run_iris_mapping_pipeline.py
```

PowerShell：

```powershell
$env:SCIWEAVE_MAPPING_TERMINUSDB_URL="http://127.0.0.1:6363"
$env:SCIWEAVE_MAPPING_TERMINUSDB_STORE="admin"
$env:SCIWEAVE_MAPPING_TERMINUSDB_USERNAME="admin"
$env:SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD="root"
python humans/competition/demo-evidence/run_iris_mapping_pipeline.py
```

完整证据（每步 MCP 请求/响应与正式的审计时间线）已写入 `demo-evidence/iris_platform_pipeline.json`。首次运行同时暴露并修复了共享留痕包的多线程访问缺陷（`ai4-fmco`），修复前写工具在真实 HTTP 部署下返回 `audit_unavailable`。

**2026-10-27 复跑**（`develop` 合入 `feature/frank-qi`，合并提交 `e54aa92`）：退出码 0、耗时 1.1s，六步时序完整，三条失败路径均返回预期错误码，`result.status: completed`、`formal_mapping_contains_t4: true`。证据文件由该次运行重新生成，并从 UTF-16LE 转为 UTF-8。

**平台链路 vs SciencePal 的分工**：本证据证明 SciWeave 治理闭环（候选→审阅→正式化→查询）在真实存储上可复现；T1 数据检查与 T2 分析执行本身仍由 `check_iris_input.py` / `run_iris_baseline.py` 承担，赛事硬门槛（SciencePal 实际承担核心任务）不变。

## 演示流程（3–5 分钟可复现脚本）

1. T1 固定并检查输入：SciencePal Agent 读取 `iris_data.csv`，按证据卡字段核验；缺列/类别计数不符/哈希不符时失败。
2. T2 执行基线分类：SciencePal 读取数据执行固定方法，产出指标与混淆矩阵并保存结果引用。
3. T3 研究人员复核并接纳：TaskNode Owner 检查方法、结果、来源引用完整性；可接纳或要求补充/重做。
4. 路线变更演示（可选 T4）：针对 150 条小样本评估稳定性，TaskNode Owner 可要求加入分层交叉验证 T4，形成 `T1 → T2 → T4 → T3`；必须提交 Mapping Proposal、展示 Diff 与影响预览，由 Project Owner 批准或驳回。
5. 失败注入：使用移除目标列的临时副本，T1 检查失败、留 Execution Record 且不产出可引用结果；恢复官方输入后普通重试成功，不创建 Proposal。
6. 驳回分支（可选）：Project Owner 驳回未验证候选，保留理由与审计事件，候选不得进入正式查询或调度。

## 待 SciencePal 补的交割物

- SciencePal 可访问项目/工作流链接；
- T2 实际运行输出（指标记录、混淆矩阵、结果文件）；
- 承接 T1/T2 的执行记录与输入/输出快照哈希；
- 人工接管点说明。

> **执行入口已就绪**：`sciencepal-runs/run_t1_t2_on_sciencepal.py`（含 README）把 `check_iris_input.py` + `run_iris_baseline.py` + 锁定数据快照交给 SciencePal 沙箱执行，轮询到终态、下载产物、核对 `status=ok`/accuracy 后落盘 `sciencepal_t1_t2_evidence.json`。已在本地用假 SciencePal 服务验证全流程（staging→run→collect→核对→证据），SciencePal 平台网络恢复即可实跑（当前仅 sciencepal.ai 超时，2026-10-28 凌晨确认）。

这些就绪后，`ai4-aaff` 的「可执行初始 Research Mapping」「最小数字数据/证据包」「计时演示脚本」「真实成功与失败/驳回路径」四个未勾选验收项才能闭合。

## 替换验证（NOAA Mauna Loa CO₂）

时间序列替换验证只作为可选实测，不作为当前提交的必要依赖。替换时需更换：数据快照与许可说明、字段校验（年/月/十进制日期/ppm/缺测标记）、分析步骤（趋势/季节分解）与指标。治理流程不变。来源：`https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv`，未核实标准许可证前不打包再分发。
