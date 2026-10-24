---
id: ai4-emfn
status: open
deps: []
links: []
created: 2026-10-24T03:02:48Z
type: chore
priority: 2
assignee: hanjiang
parent: ai4-xup8
tags: [toolkit, mcp, runtime, config]
---
# 对齐套件标准 MCP 卡片与领域管理 MCP 真实工具面

researcher-agent-toolkit/deploy-task-agent/libs/mcp-libs 三张标准卡片（draft-buffer/research-mapping/research-wiki）的工具面、环境变量与 transport/endpoint 声明仍为早期占位，与实际领域管理 MCP 和草稿箱服务不一致：卡片只声明 1 个虚构工具（draft_box_write/research_map_search/llm_wiki_lookup），真实服务各暴露 7-8 个工具；卡片未声明 transport 与 endpoint.url_env，runtime 无法推导连接方式；example-fast-agent.yaml 引用的资源名（research-map-read 等）与卡片 name 不匹配会导致 unknown_mcp_resource。本票将卡片对齐到真实工具面并验证 runtime 加载。关联 ai4-w73z（对外接口）、ai4-za77（套件）。

## Acceptance Criteria

- [ ] 三张卡片 tools 与真实服务 TOOL_DEFINITIONS/call_tool 一一对应（draft-buffer 7 工具、research-mapping 7 工具、research-wiki 8 工具），输入参数一致
- [ ] 卡片声明 transport=streamable-http 与 endpoint.url_env，environment 使用 .env.example 既有变量名
- [ ] example-fast-agent.yaml 的 allowed_domain_mcps 资源名与卡片 name 一致
- [ ] runtime 能加载标准 mcp-libs 目录，catalog 输出与真实服务工具面一致；runtime 全量测试通过

