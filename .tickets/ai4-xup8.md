---
id: ai4-xup8
status: open
deps: []
links: [ai4-x3nx, ai4-r3so, ai4-saug, ai4-iciy]
created: 2026-10-18T14:54:19Z
type: epic
priority: 1
tags: [wayfinder:map]
---
# Research Mapping 与 Wiki 领域数据模型和持久化规格地图

## Design

## Destination
形成可交给实现规划的 SciWeave 核心协作领域规格：明确 Research Mapping 与 LLM-Wiki 的数据模型和持久化规则，并逐步厘清消息队列协作、Agent 套件接入和端侧 Agent 的职责与交互边界。

## Notes
领域：版本化 Research Mapping、LLM-Wiki，以及多人和多 Agent 协作能力（消息协作、Agent 套件、端侧 Agent）。
遵循既有领域决策：两个领域治理语义可共用，但 MCP、存储、校验和审计边界独立。
地图按并列分支逐步收敛：Mapping/Wiki 持久化规格；消息协作语义；Agent 套件职责边界；端侧 Agent 角色与治理边界。新增分支目前仅建立讨论入口，保持开放、未认领，不代表已决定方案。
具体 API、算法实现、消息队列产品和部署架构不在当前目的范围内。

## Decisions so far

## Not yet specified

## Out of scope
- 具体 MCP/API 参数、冲突检测算法、消息队列产品选型、代码实现和部署架构。

**2026-10-18T15:39:58Z**

本地图及其开放分支已推送至 feature/qiyueran，当前提交 622cae7；Pull Request：docs(wayfinder): expand collaboration specification map（https://gitee.com/qi-yueran/ai4science/pulls/8，目标 develop）。旧版 PR 提交 cbe871c 保存在 backup/feature-qiyueran-pr-7。
