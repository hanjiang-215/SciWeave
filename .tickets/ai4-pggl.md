---
id: ai4-pggl
status: closed
deps: []
links: []
created: 2026-10-23T03:24:33Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-za77
tags: [implementation, ready-for-agent, task-agent, toolkit, structure, migration]
---
# 收敛 deploy-task-agent 套件目录结构


## Notes

**2026-10-23T03:24:33Z**

2026-10-23：经 Project Owner 确认，以 Frank Qi 身份在 integration/task-agent-spec 集成分支创建并实现本迁移票。

**2026-10-23T03:46:02Z**

2026-10-23：完成目录迁移。将 libs 收敛为 agent-libs，将 deploy-task-agent-skills 收敛到 skills/deploy-task-agent-skills；Agent 卡片迁入 agent-definitions/agents，新增 workflows 示例、schema.yaml、README；新增 local-agent-libs/local-mcp-libs 说明；MCP 资源目录统一为 research-mapping、research-wiki、draft-buffer；更新根 README 和技能引用。验证：runtime 12 tests、agent-libs 4 tests、mcp-libs 4 tests 全部通过，compileall、hook bash -n、git diff --check 通过。
