---
id: ai4-qula
status: open
deps: [ai4-1aeg, ai4-e959]
links: [ai4-44fk]
created: 2026-10-28T01:06:50Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-yidf
tags: [centre-control, centre-agents, agent, correctness, ready-for-agent]
---
# 治理事件落成执行记录并派发：recompute_triggered 不再只是一个计数

这是三处断链里最上游的一处。`gateway/ingest` 消费到治理事件、拉完全量候选、判定该重算，`_trigger_recompute` 返回一个整数，这个整数被打进 `json_outcome` 的日志字段，然后没有第二个读者。ingest 不写 `execution_records`（全仓 grep 计数 0），不写 inbox，不 spawn 任何进程。

同时 `gateway/subscriber` 订的是 `sciweave.task-handoff.*`——那是端侧的话题，中央根本不该订；它读 `target.id`，这也是 `ai4-derq` 记在阶段 4 的那处缺陷。两条管线的形状都对不上中央的语义。

这一片把触发接上：消费器判定需要重算时，在同一个本地事务里写一条执行记录（`queued`），落库成功才提交 consumer offset，然后派发给上一张票做出来的子进程。

**执行标识是快照审，不是单个候选。** 中央侧的目标是一次全量候选快照，标识用（域，事件，去抖窗口）这一组；租约的目标键用同一组。同一窗口内的多次候选变更合成一次预审，与 `ai4-a2ba` 定的去抖语义一致。这一条与 Task Agent 按 `task_node_id` 派发是最本质的差异，不能照抄。

规格见 `docs/superpowers/specs/2026-10-28-centre-agent-runtime-template-port-design.md` 的「触发的形状：快照审，不是按节点审」。

## Acceptance Criteria

- [ ] 一次候选事件（`candidate_created` / `candidate_head_updated`）在库里产出一条 `queued` 执行记录，并在同一流程里派发 Worker
- [ ] 去抖窗口内的第二个事件不新增执行记录，与 `ai4-a2ba` 的快照审去抖一致
- [ ] `formal_revision_published` 绕过窗口，无候选受影响时不新增记录
- [ ] 执行记录落库失败时不提交 consumer offset，消息重放
- [ ] 执行标识包含域、事件与去抖窗口，不是单个 `candidate_id`；租约目标键与之一致
- [ ] 有测试从 `consume()` 这一层断言库里的记录，不 mock 消费器自己

