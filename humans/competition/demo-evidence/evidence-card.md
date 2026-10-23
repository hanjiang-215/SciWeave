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

## T2 分析参数（已锁定待运行，未声称已运行）

演示执行前必须固定以下参数并随执行记录公开，当前仅为声明：

- 方法：预先固定的分类方法（演示待定：KNN / 逻辑回归之一），不得在录制时临时更换；
- 工具/版本：SciencePal 实际运行环境的解释器/库版本，运行后回填；
- 随机性控制：固定随机种子与确定性设置；
- 数据划分：分层训练/测试划分及比例（待定，如 70/30），划分前打乱固定种子；
- 指标：准确率、混淆矩阵、类别精度/召回（至少含混淆矩阵与准确率）；
- 完成阈值：本次演示不追求调优，固定并报告结果即可；
- 输出文件：分析结果文件与引用定位，运行后回填哈希。

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