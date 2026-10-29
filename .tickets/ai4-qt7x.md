---
id: ai4-qt7x
status: closed
deps: []
links: []
created: 2026-10-29T02:23:30Z
type: bug
priority: 1
assignee: hanjiang
---
# 网关 Worker 租约无回收、queued 无补投：进程被杀后执行永久卡住

审查报告 S1 复核成立：worker_leases 只有 INSERT/DELETE，无过期回收；下一跳只在 run_worker_process 末尾 spawn，进程死在提交终态与 spawn 之间时后继 queued 无人推进；gateway/cli.py 启动不扫描。跨进程只靠 SQLite 锁，transaction() 为延迟 BEGIN。

## Acceptance Criteria

1) 启动与周期扫描把无租约的 queued 执行补投；2) 超过阈值的租约被回收并把执行标为 failed(worker_lost)；3) 执行非 running 的孤儿租约被清掉；4) transaction() 以 BEGIN IMMEDIATE 抢写锁；5) 测试覆盖补投、回收、孤儿清理；6) 新配置写进 .env.example

