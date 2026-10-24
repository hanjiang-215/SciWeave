---
id: ai4-qnvd
status: open
deps: []
links: []
created: 2026-10-24T15:02:08Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-w73z
tags: [centre-agents, mcp, prereview, governance, implementation]
---
# 实现领域管理 MCP 预审报告追加写端 append_prereview_log

oz3s 契约已关闭并完整定义：两领域各一张预审报告表 + 失效判定表，字段对齐不共享；唯一键 (candidate_id, candidate_head, rule_set_version)；只追加不可改删；失效用追加判定表达；rule_set_version 无法解析到规则文件时返回 rule_set_missing。rlv6 只决定规则文件位置（可用环境变量配置路径），不阻塞本工具的存储层与 MCP 工具实现。本票在 w73z 范围落地 append_prereview_log：research-map 与 research-wiki 各建表、SQLiteStore 追加方法、management 工具面（centre 档）与 main.py 接线、回归测试。create_merged_candidate 另立票。

## Acceptance Criteria

- [ ] 两领域各建 mapping/wiki_prereview_report 与 _decision 表，DDL 对齐不共享
- [ ] append_prereview_log 追加报告：唯一键幂等、只追加、verdict/checks/conflict_matrix JSON
- [ ] 失效判定追加：head_moved 带 superseding_report_id、base_moved 为空；查询按 decided_at DESC 取首条
- [ ] rule_set_version 无法解析时返回 rule_set_missing 拒绝写入；规则文件路径由环境变量配置
- [ ] 工具走 centre 档位鉴权 + 写工具 fail-closed 留痕
- [ ] 两领域全量测试通过，无新增依赖

