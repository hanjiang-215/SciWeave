---
id: ai4-xkbd
status: open
deps: [ai4-g5fx]
links: [ai4-10ja, ai4-te1v, ai4-f985, ai4-2raq, ai4-edrp]
created: 2026-10-26T08:21:32Z
type: bug
priority: 1
assignee: hanjiang
parent: ai4-10ja
tags: [implementation, centre-control, handoff, notification, ready-for-agent]
---
# 人工通知收件人取 principal_id

## What to build

人工通知发给真正要动手的那个人。现在四处把 `mapping_domain_id` 当收件人传给 email-service，而它需要的是 `principal_id`，解析不到任何联系人。

规格见 [`2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md`](../docs/superpowers/specs/2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md)。

## Acceptance Criteria

- [ ] `executor_refs` 为空时产出 `workflow_binding_required`，收件人为该节点 `task_owner_id`。
- [ ] `executor_refs` 指向未登记 `agent_id` 时产出 `workflow_load_failed`，收件人为该节点 `task_owner_id`。
- [ ] 执行者已注销、无可用实例、或只配置人工处理时产出 `agent_unavailable`，收件人为该节点 `task_owner_id`。
- [ ] 派发成功的节点无后继时产出 `task_terminal_summary`，收件人为 `FormalSnapshot.latest_published_by`。
- [ ] 每条通知只有一个收件人。
- [ ] `task_owner_id` 缺失时不生成通知，`PendingHandoff` 保持 `waiting`，并记录 `recipient_unresolved:task_owner_id_missing`。
- [ ] `latest_published_by` 缺失时同样不生成通知，保持 `waiting` 并记录可观察原因。
- [ ] 发送前经 Registry 校验 `principal_id` 存在且 `active`；校验不通过时不建 dispatch、记错误、保持 `waiting`。
- [ ] Registry 不可用时 fail-open 照发，不因为校验服务不可用而停掉整条通知链路。
- [ ] 四种场景产出三种 kind，且三种 kind 的正文能说明收件人下一步该做什么。
- [ ] 不再有任何调用点传 `mapping_domain_id` 作为收件人。
- [ ] 新增测试覆盖四类场景、`task_owner_id` 缺失、Registry 校验失败、Registry 不可用；修复前多项失败。
- [ ] 既有 9 项测试仍通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 收件人角色由通知类型决定，不由调用方选择。这是 `ai4-te1v` 第四轮的裁决，`GLOSSARY.md` 的「通知收件人」也写了。
- 四种场景三种 kind，因为它们要求收件人做的事不同：绑 Workflow、修配错的 `agent_id`、自己上手。合并成一种，邮件就说不出下一步。
- `latest_published_by` 的真实数据来自 research-map，由 `ai4-2raq` 与 `ai4-edrp` 提供；本票在测试里直接构造 `FormalSnapshot`。
- `task_owner_id` 缺失是数据损坏，不是配置待补。宁可不动，也不能把任务通知给一个随机的人。
- fail-open 的取舍：校验是为了减少错发，不是阻止正常投递。校验服务挂了就停掉通知，代价大于收益。
- 命名见 [ADR-0004](../docs/adr/0004-po-recipient-from-latest-approver.md)：`latest_published_by` 回答「最近一次批准者是谁」，不是「谁被任命为负责人」。

**2026-10-26 负责人转交（hanjiang 操作，按项目所有者指示）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据：项目所有者 2026-10-26 指示，Frank Qi 名下 coordinator / handoff / message-envelope 链路的 11 张 open 票统一转交 hanjiang 推进与收口。原负责人 Frank Qi，转交时间 2026-10-26T15:41:00Z。转交只变更归属并记录，不改写正文、验收标准与既有决策。
