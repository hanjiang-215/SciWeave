---
id: ai4-7cmr
status: open
deps: [ai4-g5fx]
links: [ai4-10ja, ai4-zc85, ai4-te1v]
created: 2026-10-26T08:21:32Z
type: bug
priority: 1
assignee: hanjiang
parent: ai4-10ja
tags: [implementation, centre-control, handoff, ready-for-agent]
---
# 修复派发幂等与状态回退

## What to build

同一节点版本在连续多个正式版本发布下只派发一次，且已经 `done` 的交接不会因为上游再升版本被改回 `waiting`。现在这两件事同时坏着：三个正式版本会导致三次派发，Task Agent 重复执行。

规格见 [`2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md`](../docs/superpowers/specs/2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md)。

## Acceptance Criteria

- [ ] 去重键改为 `mapping_domain_id:task_node_id:target_node_version_ref:message_type`，不含触发版本。
- [ ] 同一节点版本连续三个正式版本发布，只产生 1 条 `HandoffDispatch` 和 1 条 `task_handoff_ready`。
- [ ] `PendingHandoff` 进入 `done` 后，上游版本升级或再次重算都不把它改回 `waiting`。
- [ ] 允许的状态迁移：`waiting → ready → dispatched_unknown → done`；任意非终结态 → `superseded` / `failed`。非法迁移被拒绝且不改动既有状态。
- [ ] `done` 之后同版本重算不新建 dispatch 记录。
- [ ] 新增测试：三个正式版本一次派发、`done` 不回退、非法迁移被拒；三项在修复前均失败。
- [ ] 既有 9 项测试仍通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 两个修复必须同时落地。只去掉触发版本，`done` 仍会被重算覆盖回 `waiting`，新触发下再次派发；只加状态守卫，同一触发版本重放仍会重复。任缺其一，「三版一次」的验收都过不了。
- 状态迁移的允许集合来自 `ai4-zc85` 已关闭的规格，不要在实现中自行放宽。
- 非法迁移的处理是「拒绝并保留原状态」，不是抛异常中断整轮重算——一轮重算里其他节点仍然应该推进。

**2026-10-26 负责人转交（hanjiang 操作，按项目所有者指示）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据：项目所有者 2026-10-26 指示，Frank Qi 名下 coordinator / handoff / message-envelope 链路的 11 张 open 票统一转交 hanjiang 推进与收口。原负责人 Frank Qi，转交时间 2026-10-26T15:41:00Z。转交只变更归属并记录，不改写正文、验收标准与既有决策。
