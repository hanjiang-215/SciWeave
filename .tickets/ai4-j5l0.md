---
id: ai4-j5l0
status: closed
deps: []
links: []
created: 2026-10-23T03:54:13Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-3qiv
tags: [implementation, ready-for-agent, task-agent, toolkit, structure, migration]
---
# 将本地扩展资源移入 libs 目录


## Notes

**2026-10-23T03:54:13Z**

2026-10-23：以 Frank Qi 身份执行。将 local-agent-libs 与 local-mcp-libs 移入 libs/，保持外部 LOCAL_* 路径扩展能力。

**2026-10-23T03:55:14Z**

2026-10-23：完成本地扩展资源迁移。local-agent-libs 与 local-mcp-libs 已移动到 libs/，根 README 和两个说明文件已同步；LOCAL_AGENT_LIBS/LOCAL_MCP_LIBS 外部目录扩展方式保持不变。验证：runtime 12 tests、agent-libs 4 tests、mcp-libs 4 tests 全部通过，compileall、hook bash -n、git diff --check 通过。
