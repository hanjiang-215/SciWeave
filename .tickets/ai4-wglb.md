---
id: ai4-wglb
status: closed
deps: []
links: []
created: 2026-10-19T06:47:28Z
type: epic
priority: 1
assignee: hanjiang
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# Research Mapping MCP 依赖图最小适配边界

承接 Gateway 最小底座与 Agent Kit 交付地图；本票只解决一个实现前置决策，不直接编写产品代码。

## Design

## Question
在 Gateway 底座稳定后，Research Mapping/依赖图 MCP 首次接入应暴露哪些最小只读和受控写入能力？需要明确依赖图领域逻辑留在领域服务，Gateway 只负责工具调用授权、超时、错误、审计和结果引用的边界。

## Acceptance Criteria

形成依赖图 MCP 适配器的首版工具边界、输入输出引用、权限、超时、失败和审计规则；不把 Mapping 节点/边治理逻辑复制进 Gateway。


## Notes

**2026-10-19T06:58:30Z**

2026-10-19：根据目标收敛，本阶段只实现 Gateway + 最小 fast-agent-mcp 执行闭环；Research Mapping/依赖图 MCP 不属于当前地图，转入后续独立阶段。

**2026-10-20T07:44:05Z**

负责人转交（2026-10-20）：原负责人 Frank Qi。按项目所有者指示，产品与需求、Research Mapping、LLM-Wiki 模块的工单负责人统一为 hanjiang（即 zhanyunfei）；本票主模块为 Research Mapping，因此一并转交。
