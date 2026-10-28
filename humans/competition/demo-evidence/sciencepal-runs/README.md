# SciencePal T1/T2 正式执行包（ai4-aaff 硬门槛交付物）

> 状态：2026-10-27 晚准备。**SciencePal 平台本机当前不通（仅 sciencepal.ai 超时，其他外网正常），
> 此包为网络恢复即跑的成品**；跑通后会回填 `sciencepal_t1_t2_evidence.json` 并更新证据卡。

把 UCI Iris 演示的 **T1 输入检查**（`check_iris_input.py`）与 **T2 基线分类**
（`run_iris_baseline.py`）交给 **SciencePal 沙箱真实执行**，满足赛事「SciencePal 实际承担
核心数据检查或分析执行，仅写文案不合格」的硬门槛。

## 它做了什么

1. 核对本机 `iris_data.csv` 快照哈希与证据卡锁定值一致（防止把非锁定数据送给平台）；
2. 把两个脚本 + 数据复制进 bridge 的 `SCIENCEPAL_WORKSPACE/inputs/`（`resolve_input` 强约束）；
3. 向 SciencePal 发起两次 run：T1 执行输入检查、T2 执行基线分类，指令要求把标准输出原样保存为
   `/outputs/t1_check_result.json` 与 `/outputs/t2_baseline_result.json`；
4. 轮询到终态 → 下载产物 → 断言 T1 `status=ok`、T2 含 accuracy，逐项核对；
5. 全部通过后把两次 run 的 `run_id`、产物哈希、时间戳写入 `sciencepal_t1_t2_evidence.json`。

**不打印、不落盘 token；token 只从 bridge `.env` 读取。**

## 运行

```powershell
# 在 bridge 项目目录下用其 venv 执行
cd sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/custom-mcp/sciencepal-bridge
uv run --env-file .env python D:/project/AI4Sci/humans/competition/demo-evidence/sciencepal-runs/run_t1_t2_on_sciencepal.py `
  --bridge . `
  --workdir D:/project/AI4Sci/humans/competition/demo-evidence
```

前置条件：

- SciencePal 平台可达（`Test-NetConnection sciencepal.ai -Port 443`）；
- bridge 目录 `.env` 已填 `SCIENCEPAL_ACCESS_TOKEN`（gitignored，不入库）；
- `--workdir` 目录有 `iris_data.csv`、`check_iris_input.py`、`run_iris_baseline.py`（demo-evidence 自带）。

退出码：`0` 成功（两次 run 均 completed 且产物核对通过）；`1` 配置/用法错误；`2` 超时；`3` run 失败或产物核对不通过。

## 产物核对口径

| 阶段 | 断言 |
| --- | --- |
| T1 | 产物为 JSON、含 `status` 与 `input_snapshot_sha256`、`status=ok` |
| T2 | 产物为 JSON、含 `status`、`method`、`accuracy` |
| 证据文件 | `sciencepal_t1_t2_evidence.json`（run_id + 产物哈希 + 时间戳） |

失败时 stderr 输出 `{"error": {...}}` JSON，便于挂到 fer 票与 PR 评论。

## 与证据卡/工业票的衔接

- 证据卡：`humans/competition/demo-evidence/evidence-card.md` 的「待 SciencePal 补的交割物」
  （项目/工作流链接、T2 实际运行输出、执行记录与快照哈希、人工接管点说明）由本包产出；
- `ai4-aaff` 验收项「SciencePal 实际承载核心 Agent/任务的运行链接、输出及执行记录」由本包闭合；
- `ai4-jckq`（跨 harness 接入）与 `ai4-roow`（执行报告回写地图）复用同一 bridge。