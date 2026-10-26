---
id: ai4-n7js
status: open
deps: []
links: []
created: 2026-10-26T18:38:14Z
type: bug
priority: 1
assignee: hanjiang
tags: [bug, centre-control, research-wiki]
---
# research-wiki 的生产入口把只读存储装配给候选写入链路

src/main.py 用 TerminusDBResourceStore 构造 ResourceReviewService 与后续服务，而 create_candidate_snapshot/read_branch_head/create_formal_snapshot 只存在于 TerminusDBWikiCandidateStore。结果 submit_wiki_candidate 恒返回 result_unknown（异常被 candidate_submission 吞掉），decide_wiki_review 恒 candidate_head_changed，formalize_wiki 恒失败。

## Acceptance Criteria

main.py 装配 TerminusDBWikiCandidateStore。|新增装配测试：按 main.py 的方式构造服务图并跑通 提交→审核→正式化。|验证命令与结果回写本票。

