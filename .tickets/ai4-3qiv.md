---
id: ai4-3qiv
status: closed
deps: []
links: []
created: 2026-10-23T03:51:14Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-pggl
tags: [implementation, ready-for-agent, task-agent, toolkit, structure, migration]
---
# 收敛 Task Agent libs 与技能组目录层级


## Notes

**2026-10-23T03:51:14Z**

2026-10-23：以 Frank Qi 身份在 integration/task-agent-spec 分支执行。迁移目标：agent-libs 与 mcp-libs 移入 libs/；skills/deploy-task-agent-skills 移到套件根目录；删除 skills 目录。

**2026-10-23T03:52:28Z**

2026-10-23：完成目录层级迁移。agent-libs 与 mcp-libs 已移动到 libs/ 下；deploy-task-agent-skills 已移动到套件根目录；skills 目录已删除。同步更新 README、资源和技能引用。验证：runtime 12 tests、agent-libs 4 tests、mcp-libs 4 tests 全部通过，compileall、hook bash -n、git diff --check 通过；旧目录不存在，新目录存在。
