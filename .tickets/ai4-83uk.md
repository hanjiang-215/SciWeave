---
id: ai4-83uk
status: closed
deps: [ai4-eikj]
links: [ai4-o2n3]
created: 2026-10-23T02:28:34Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-o2n3
tags: [implementation, ready-for-agent, task-agent, work-agent, toolkit, multi-agent, fast-agent]
---
# mcp-libs 标准 MCP 资源与本地扩展

## Parent

研究员端侧 Task Agent 与 deploy-task-agent-skills 规格（ai4-o2n3）。

## What to build

提供平台标准 MCP 资源和研究员本地扩展能力。标准资源覆盖 Research Mapping、LLM-Wiki 和中央草稿箱，包含工具目录、输入输出说明、调用示例、允许场景、失败处理和环境变量约定；研究员可以通过 `local-mcp-libs` 增加自定义 MCP 资源。资源应能被 Agent 定义和工作流配置引用，但不实现领域 MCP 服务本身。

## Blocked by

- Agent 定义与工作流配置模型（ai4-eikj）

## Acceptance Criteria

- [ ] Research Mapping、LLM-Wiki 和草稿箱各有标准 MCP 资源目录与可读工具说明。
- [ ] MCP 地址、令牌和服务配置只通过环境变量提供。
- [ ] Agent 定义能够引用标准和本地 MCP 资源，并得到可观察的工具目录。
- [ ] 本地 MCP 资源可扩展标准资源，冲突和版本不兼容有稳定错误。
- [ ] 测试使用假 MCP 描述或假客户端，不连接真实领域服务。
- [ ] 本票不新增或修改领域 MCP 服务实现。

## Notes

**2026-10-23T03:02:13Z**

2026-10-23：完成 mcp-libs 标准 MCP 资源与本地扩展。新增 Research Mapping、LLM-Wiki、draft-box 资源目录和工具目录注册表，支持 LOCAL_MCP_LIBS、兼容版本覆盖及稳定冲突错误；Agent 配置可观察 mcp_catalog。验证：mcp-libs 4 tests passed，runtime 8 tests passed，git diff --check 通过。
