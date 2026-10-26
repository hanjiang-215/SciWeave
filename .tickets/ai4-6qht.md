---
id: ai4-6qht
status: open
deps: []
links: []
created: 2026-10-26T18:38:14Z
type: bug
priority: 1
assignee: hanjiang
tags: [bug, centre-control, buffer]
---
# 草稿箱 submit_draft 分两次提交，失败后草稿不可再提交也不可审核

buffer/src/draft_buffer/service.py 先写 submitted 状态并记 submitted_commit，再写 final_commit；两次之间失败会留下 status=submitted 且 submitted_commit 为空、没有 Operation 行的草稿，重试撞 invalid_transition，审核也过不了。

## Acceptance Criteria

状态转移与幂等记录在同一次提交里落地。|补测试：第二次写失败后草稿仍可重试提交。

