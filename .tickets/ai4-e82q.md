---
id: ai4-e82q
status: closed
deps: []
links: []
created: 2026-10-29T01:43:45Z
type: bug
priority: 1
assignee: hanjiang
---
# wiki 预审回查缺 base 且无 ORDER BY，候选永久 report_stale

技术审查 P1-1：research-wiki/src/llm_wiki/sqlite_store.py:196-202 append_prereview_report 唯一键含 base 但回查 SELECT 不含 base 且无 ORDER BY；current_prereview_report/prereview_status 亦无 ORDER BY。与 research-map 已修 ai4-sf8l 同类漂移。

## Acceptance Criteria

回查与 UNIQUE 键纳入 base_formal_revision_id；相关性查询加 ORDER BY created_at DESC,rowid DESC LIMIT 1；测试覆盖 base 移动后旧报告不再命中。
## Notes

2026-10-29 hanjiang：已修复，提交 1d5825c。

- 这是 research-map 已修（ai4-sf8l）而 wiki 未同步的漂移：wiki_prereview_report 唯一键与回查补上 ase_formal_revision_id，使 ase_moved 后的复审落成新行而不是被 INSERT OR IGNORE 丢掉。
- current_prereview_report / prereview_status 加 ORDER BY created_at DESC, rowid DESC LIMIT 1，不再取任意行。
- 新增 _migrate_prereview_report_key：旧库三列键自动重建为四列键并保留全部行。

验证：esearch-wiki 152 passed，新增 PrereviewBaseKeyTests（base 移动后新报告另起一行、当前报告取最新）。