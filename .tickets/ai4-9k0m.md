---
id: ai4-9k0m
status: open
deps: []
links: []
created: 2026-10-26T18:38:14Z
type: bug
priority: 1
assignee: hanjiang
tags: [bug, centre-control, centre-agents]
---
# centre-agents 消费循环：坏信封打死进程、逐条 commit 实际提交整批

ingest 的 run_loop 对 GovernanceEnvelopeError 无捕获，一条坏消息让进程退出且 offset 不提交，重启后 crash loop。三条消费循环（ingest、subscriber、centre-agents）每处理一条就调 consumer.commit()，而 poll 一次拉 100 条，commit 提交的是当前位置，崩溃时其余消息被静默标记已消费。

## Acceptance Criteria

run_loop 捕获 GovernanceEnvelopeError、记录观测后 commit 并继续；只有传输或领域异常才中断。|commit 改为按 TopicPartition 精确提交，或整批处理完再提交。|补测试：坏信封不中断循环；处理第 1 条后崩溃时其余消息仍可重放。

