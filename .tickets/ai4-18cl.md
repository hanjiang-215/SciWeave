---
id: ai4-18cl
status: closed
deps: []
links: []
created: 2026-10-29T05:08:31Z
type: bug
priority: 3
assignee: hanjiang
---
# start.ps1 启动期端口复用竞态

E2E 观察4：上一轮进程未完全释放端口时 registry/email 可能 bind 失败退出。需 start.ps1 启动前对目标端口做占用探测/重试。

## Acceptance Criteria

1) 启动前探测目标端口；2) 占用时等待/重试或明确报错，不静默失败；3) 幂等可重复执行

