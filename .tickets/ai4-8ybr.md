---
id: ai4-8ybr
status: closed
deps: [ai4-oebi, ai4-upsm]
links: [ai4-8k4y]
created: 2026-10-21T12:15:04Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, centre-agents, formalization]
---
# 正式版本推进与批准事件校验

Project Owner 批准后，中央 Agent 核对批准事件、候选 head、基准版本、冲突检查与影响预览，再推进正式版本，并在正式化后触发下游交接。

## Design

依据「Mapping Proposal 生命周期」与「Task Agent 与审核人协作及返修流程」：候选或仅被 Owner 接纳的内容不得进入正式查询或正式调度；PO 正式发布后任务才结束并沿依赖边发出交接。推进由领域自己的管理 MCP 完成，不是中央 Agent 直接写库。

待定：批准事件的表示形式、推进失败（rebase 冲突）后的状态。

## Acceptance Criteria

- 无批准事件时拒绝推进
- 候选 head 或基准版本不一致时拒绝推进
- 推进只经对应领域的管理 MCP，不跨域
- 正式化成功后才发出下游交接


## Notes

**2026-10-21T12:48:15Z**

2026-10-21 关闭：PO 批准后的正式版本推进改由 Project Owner 通过自己的 MCP 完成，不经过中央 Agent。中央 Agent 只做候选版本的预审与合并。依据见 docs/data-flow/centre-agent-scope-reduction.md。
