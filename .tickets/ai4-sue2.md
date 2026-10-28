---
id: ai4-sue2
status: open
deps: []
links: [ai4-349h]
created: 2026-10-28T05:57:39Z
type: bug
priority: 1
assignee: Frank Qi
parent: ai4-yidf
tags: [centre-control, centre-agents, mcp, auth]
---
# 中央 Agent 的 MCP 卡片令牌没有变成请求头

卡片的 environment 里列了 *_MCP_TOKEN，但 fast-agent 的 mcp.servers 渲染器只写 transport 与 url，令牌不会变成 Authorization 头。领域 MCP 校验 Bearer，因此真机联调时每次工具调用都会 401。

这条在部署模板（deploy-task-agent）与中央侧同时存在，是同一种形状复制的两处。ai4-349h 只声明了它，没有修。

