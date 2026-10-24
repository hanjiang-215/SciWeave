# SciWeave 默认科研示例场景：最小数字证据卡

> 状态：输入快照与 T1 检查已固化（2026-10-23）；T2 分析执行参数已锁定为待运行声明，未声称已运行。SciencePal 实际承载执行仍是赛事硬门槛，见下方「待 SciencePal 补的交割物」。
>
> 关联工单：`ai4-aaff`（SciWeave 默认科研示例场景与验证证据）

## 已固化的输入快照

| 项 | 值 |
| --- | --- |
| 主演示数据集 | UCI Iris（分类任务，150 条，4 个连续特征，3 类，无缺失） |
| 官方 URL | `https://archive.ics.uci.edu/static/public/53/data.csv` |
| DOI | `10.24432/C56C76` |
| 许可证 | CC BY 4.0（演示须署名并链接许可证） |
| 快照文件 | `demo-evidence/iris_data.csv`（4,615 字节） |
| 快照 SHA-256 | `daaeb5e3e889d07fbdd44544f5a39fe2372a07172e25899d577be0ad74df9e65` |

## T1 数据检查（已运行，2026-10-23）

命令：

```text
python humans/competition/demo-evidence/check_iris_input.py humans/competition/demo-evidence/iris_data.csv
```

结果：`status: ok`，150 行、4 个特征列齐全、3 类各 50 条、无缺失值、快照哈希匹配官方文件。完整 JSON 见 `demo-evidence/iris_input_check.json`。

**失败注入样本**：`demo-evidence/iris_data_failure_inject.csv` 是移除目标列的临时副本，用于演示 T1 拦截。运行同一检查脚本得到 `status: failed`、`reason_code: source_hash_mismatch`，退出码 1，不产出后续分析结果；恢复官方输入后重试成功。失败记录见 `demo-evidence/iris_input_failure.json`。这对应演示脚本第 4 段「失败注入 + 普通重试」。

## 最小数字证据卡（首版字段）

| 字段 | 值 |
| --- | --- |
| dataset_name | UCI Iris（UCI ML Repository） |
| doi | `10.24432/C56C76` |
| license | CC BY 4.0，须署名并链接许可证 |
| source_url | 见上表官方 URL |
| acquired_at | 2026-10-23 |
| input_snapshot_sha256 | `daaeb5e3...df9e65` |
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
| 输入快照 | `daaeb5e3...df9e65`（与 T1 一致） |

命令：

```text
python humans/competition/demo-evidence/run_iris_baseline.py humans/competition/demo-evidence/iris_data.csv
```

结果文件：`demo-evidence/iris_baseline_result.json`。

**SciencePal 硬门槛不变**：以上证明演示闭环在平台外可复现，但赛事要求 SciencePal 实际承接核心数据检查或分析执行。SciencePal 接入后应封装该脚本或同参数实现，并回填真实运行环境的解释器/库版本、输出定位与执行记录；不得以本机结果冒充 SciencePal 实演。

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

这些就绪后，`ai4-aaff` 的「可执行初始 Research Mapping」「最小数字数据/证据包」「计时演示脚本」「真实成功与失败/驳回路径」四个未勾选验收项才能闭合。

## 替换验证（NOAA Mauna Loa CO₂）

时间序列替换验证只作为可选实测，不作为当前提交的必要依赖。替换时需更换：数据快照与许可说明、字段校验（年/月/十进制日期/ppm/缺测标记）、分析步骤（趋势/季节分解）与指标。治理流程不变。来源：`https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv`，未核实标准许可证前不打包再分发。