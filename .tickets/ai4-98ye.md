---
id: ai4-98ye
status: open
deps: [ai4-g5fx]
links: [ai4-10ja, ai4-te1v, ai4-zc85]
created: 2026-10-26T08:21:33Z
type: bug
priority: 1
assignee: hanjiang
parent: ai4-10ja
tags: [implementation, centre-control, handoff, ready-for-agent]
---
# 统一快照错误在两个入口的处置

## What to build

同一个快照读取失败，在启动扫描和重试路径上应该留下同一种状态。现在启动扫描静默跳过，重试路径记 `result_unknown`，事后无法判断「真没派发」还是「读不到快照」。

规格见 [`2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md`](../docs/superpowers/specs/2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md)。

## Acceptance Criteria

- [ ] `SnapshotUnavailableError` 与 `SnapshotInconsistentError` 在两个入口都被视为可重试，保留既有事实，等待下次事件或启动扫描。
- [ ] `NoSuchRevisionError` 在两个入口的处置一致，且不把已派发事实改成失败。
- [ ] `startup_scan` 遇可重试错误时不再静默跳过，至少留下可观察记录。
- [ ] `_retry_dispatch` 遇可重试错误时保持 `result_unknown`，与启动扫描的口径一致。
- [ ] 「快照不可读」与「派发确定失败」在 dispatch 状态上可区分。
- [ ] 错误处置规则收敛到一处，两个入口调用同一函数，不各写一份 `except`。
- [ ] 新增测试：同一错误分别经两个入口，产生一致状态；修复前两者不一致。
- [ ] 既有 9 项测试仍通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 这不是把两个 `except` 抄成一样的。要判断的是「哪些错误可重试」这个策略，策略只该有一份，否则下次调整会漏掉一边。
- 静默跳过是当前最严重的问题：它让一个可观察的失败变成不可观察，运维看不到任何痕迹。
- 只有确定不可恢复时才转 `failed`。`failed` 的语义是「代码能做的都做完了」，不能拿它当「这次没读出来」的垃圾桶。

**2026-10-26 负责人转交（hanjiang 操作，按项目所有者指示）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据：项目所有者 2026-10-26 指示，Frank Qi 名下 coordinator / handoff / message-envelope 链路的 11 张 open 票统一转交 hanjiang 推进与收口。原负责人 Frank Qi，转交时间 2026-10-26T15:41:00Z。转交只变更归属并记录，不改写正文、验收标准与既有决策。
