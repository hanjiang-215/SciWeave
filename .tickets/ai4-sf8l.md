---
id: ai4-sf8l
status: open
deps: []
links: []
created: 2026-10-26T18:38:14Z
type: bug
priority: 1
assignee: hanjiang
tags: [bug, centre-control, research-map]
---
# research-map 预审：base_moved 失效后无法重算，候选被永久卡住

current_prereview_report 在任何决策行存在时返回 None，绕过去重守卫；append_prereview_report 的 INSERT OR IGNORE 命中唯一键后返回旧行，新判据被丢弃且 duplicate 报 False，prereview_status 仍是 report_stale。docs/data-flow/centre-agent.md 要求失效后下一次预审重算。

## Acceptance Criteria

失效判定与报告身份解耦，或把 revision 计入唯一键。|append_report 只在真正插入时返回 duplicate=False。|prereview_status 按 rule_set_version/created_at 确定取哪一条。|补测试：base_moved 后重算写入新报告。

