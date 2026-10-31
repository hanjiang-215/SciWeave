---
id: ai4-5dq4
status: in_progress
deps: []
links: []
created: 2026-10-31T05:37:34Z
type: feature
priority: 2
assignee: Frank Qi
tags: [toolkit, release]
---
# 套件发版工具入库与发版技能

sci-weave/toolkits/release-scripts/ 下的五个发版脚本（pack/publish/release/install-suite 与 README）目前只存在于本地工作区，从未入库；同时缺少一个给 Agent 用的发版技能，每次发版仍要人工回忆步骤与前置条件。

## Acceptance Criteria

五个脚本入库并可执行（shell 语法检查通过）；新增发版技能在 .cursor/skills 与 .dsh/skills 两处可用；设计规格写入 docs/superpowers/specs/ 并说明 .dsh 为派生副本

