---
id: ai4-68cv
status: open
deps: []
links: []
created: 2026-10-24T03:56:02Z
type: chore
priority: 2
assignee: hanjiang
parent: ai4-xup8
tags: [chore, cleanup, docs]
---
# 清理旧目录残留与修正导航文档

承接 2026-10-22 项目审查的目录与文档清理建议：删除 sci-weave/llm-wiki、sci-weave/research-mapping、sci-weave/gateway 三个已迁移的空目录（只剩 .venv/.pytest_cache 等构建残留）；删除根目录 .pytest_cache 并加入 .gitignore；更新 centre-control/README.md 的模块状态（buffer/dashboard-api/web-ui 已实现）；修正 research-map/research-wiki 两个领域 README 的目录清单（此前重复列 sqlite_store/terminus_store，且未列 candidate_submission/management/management_mcp/dashboard_source 等已实现模块）；修正 2026-10-21-mapping-wiki-formalization-delivery-design.md 中 TerminusDB 验证服务旧路径。registery 目录拼写问题因涉及 ai4-ujvn/ai4-t2wc 的路径引用，不擅自改名，留待该票负责人确认。

## Acceptance Criteria

- [ ] 三个旧目录与根 .pytest_cache 已删除且 git 状态干净
- [ ] .pytest_cache 已加入 .gitignore
- [ ] centre-control/README.md 模块状态与当前实现一致
- [ ] 两个领域 README 目录清单无重复且覆盖已实现模块
- [ ] spec 文档 TerminusDB 路径修正为 sci-weave/service/terminusdb

