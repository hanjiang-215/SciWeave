# 示例

- `task-packet.json`：交给 harness 的任务包；`sha256` 先算再填，`formal_revision_id` 用交接消息里的 `trigger_revision_id`。
- `execution-report.json`：harness 跑完 SciencePal 后写的报告；`run_id`、产物路径与 `sha256` 必须来自真实 `collect` 结果，不能编。

这两个文件只作形状参考，不参与运行。
