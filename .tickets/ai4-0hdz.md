---
id: ai4-0hdz
status: closed
deps: []
links: []
created: 2026-10-29T03:03:27Z
type: feature
priority: 1
assignee: hanjiang
---
# wiki 缺少首个正式版本引导（bootstrap）入口

技术缺陷报告 B3：wiki 候选提交要求 base_formal_revision_id 必须已存在（candidate_submission.py:103-105），但没有任何入口能创建第一个正式版本，形成先有鸡还是先有蛋死结，看板报 no_current_pointer、0 文档；此前靠手工脚本 seed 绕过。需提供受 owner 权限保护的 MCP 工具（含写入首个正式版本并初始化 TerminusDB schema），无 current pointer 时原子建立基线。

## Acceptance Criteria

1) 新增 bootstrap_wiki 工具，仅 project_owner/centre 可调；2) 无 current pointer 时写入首个正式版本并初始 schema，有 pointer 时拒绝且不改动；3) 幂等：重复调用安全；4) 单测覆盖成功/拒绝/幂等；5) research-wiki 全量测试通过

