---
id: ai4-1aeg
status: open
deps: []
links: []
created: 2026-10-28T01:06:21Z
type: bug
priority: 1
assignee: Frank Qi
parent: ai4-yidf
tags: [centre-control, centre-agents, correctness, ready-for-agent]
---
# 中央 Worker 租约带过期时间：崩溃后不必手工删库

中央侧的 `worker_leases` 只有三列：`task_node_id`、`execution_id`、`acquired_at`。读取侧唯一的判据是「这一行在不在」，全仓没有一处过期判断。

后果是确定的：一次 Worker 崩溃、一次订阅器被 kill、一次派发过程中的异常退出，那个目标就永久拿不到租约，永久跑不动。数据库里留着一行谁也清不掉的记录，而处置面上看不出任何异常。

端侧已经解决了这个问题（`work_agent_runtime/lease.py` 有 `expires_at`、`BEGIN IMMEDIATE`、`DEFAULT_LEASE_SECONDS`）。ADR-0002 明说「Worker Lease 必须两边一起改」，这一片就是把它补上。

规格见 `docs/superpowers/specs/2026-10-28-centre-agent-runtime-template-port-design.md` 的「租约写入过期时间」。

## Acceptance Criteria

- [ ] `worker_leases` 增加 `expires_at`，写入用 `BEGIN IMMEDIATE` 事务，不靠重试
- [ ] 「有效租约」的判据从「行存在」改成「行存在且未过期」
- [ ] 过期租约可被下一次派发覆盖，并写一条审计事件说明是回收而非新领
- [ ] 未过期租约仍被拒绝，第二个派发不得覆盖它
- [ ] 有测试用可控时钟分别覆盖「已过期回收」「未过期拒绝」两条路径
- [ ] 迁移对已有数据库可用（`CREATE TABLE IF NOT EXISTS` 不够，需要 ALTER 或重建）

