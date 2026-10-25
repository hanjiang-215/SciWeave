---
id: ai4-qnvd
status: closed
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

- [x] 两领域各建 mapping/wiki_prereview_report 与 _decision 表，DDL 对齐不共享
- [x] append_prereview_log 追加报告：唯一键幂等、只追加、verdict/checks/conflict_matrix JSON
- [x] 失效判定追加：head_moved 带 superseding_report_id、base_moved 为空；查询按 decided_at DESC 取首条
- [x] rule_set_version 无法解析时返回 rule_set_missing 拒绝写入；规则文件路径由环境变量配置
- [x] 工具走 centre 档位鉴权 + 写工具 fail-closed 留痕
- [x] 两领域全量测试通过，无新增依赖

## Notes

**2026-10-24 实现与验证（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

提交 `605ea1a`。改动：

- `research-map` / `research-wiki` 各新增 `mapping/wiki_prereview_report` 与 `_decision` 两张表（按 `ai4-oz3s` DDL 骨架，字段对齐、不跨领域共享）。
- 新增 `prereview.py`（两领域对称）：`MappingPrereviewLog` / `WikiPrereviewLog` 提供 `append_report`（唯一键 `(candidate_id, candidate_head, rule_set_version)` 幂等、只追加、checks/verdict/conflict_matrix 存 JSON）与 `append_decision`（`head_moved` 必带 `superseding_report_id`、`base_moved` 为空；当前有效报告由 `ORDER BY decided_at DESC, rowid DESC LIMIT 1` 推出）。`resolve_rule_set` 从配置的规则目录读取 `<version>.json`，缺失或无法解析返回 `rule_set_missing` 拒绝写入。
- `sqlite_store.py`：两领域各加 `append_prereview_report` / `append_prereview_decision` / `current_prereview_report`。
- `management.py`：工具面增加 `append_prereview_log`（mapping）/ `append_wiki_prereview_log`（wiki），`centre` 档位，写入 `_WRITE_TOOLS` 与 `_TOOL_CAPABILITIES`；写工具走 fail-closed 留痕（invoked/completed）。`reason` 存在时走失效判定分支，否则追加报告。
- `config.py`：两领域各加 `prereview_rules_dir`（`SCIWEAVE_MAPPING/WIKI_PREREVIEW_RULES_DIR`）；`.env.example`、README 目录清单同步。
- `main.py`：接线 prereview_log。

验证（本机实测）：

- research-map：`tests.test_prereview` 8 项 + `tests.test_management` 19 项 + 全量 105 项通过（5 跳过）。
- research-wiki：`tests.test_prereview` 7 项 + `tests.test_management` 17 项 + 全量 111 项通过（4 跳过）。
- `compileall` 与 `git diff --check` 通过；无新增依赖。

边界：本票只实现 `append_prereview_log` 写端；`create_merged_candidate` 另立票。规则文件位置由 `rlv6`（Frank Qi）最终收口，当前实现用环境变量路径 + `rule_set_missing` 兜底，收口后仅需配置路径。`he04`/`5z9e` 写端验收可随本工具复验。

