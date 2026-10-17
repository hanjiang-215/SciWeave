---
id: ai4-m0vt
status: open
deps: [ai4-ay0e, ai4-r3so]
links: [ai4-e257, ai4-vbnr]
created: 2026-10-17T15:21:05Z
type: grilling
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:grilling, mapping, execution, product, ai4science]
---
# 首版任务执行、交接与失败恢复模型

明确 SciWeave 首版围绕 Research Mapping 的任务执行语义：任务状态、人员/Personal Agent/Task Agent 分派、MCP Submission、Execution Record、结果提交、TaskNode Owner 审核、重试、转交、人工接管、失败分类和路线改变触发 Mapping Proposal。只确定产品与领域规则，不进入消息队列、模型选择或 API 实现。

## Design

建议围绕一个可复现演示闭环定义最小状态集和状态转换；普通执行失败与改变研究假设、前置条件或路线的失败必须可区分；执行结果的第一阶段接纳审核与 Project Owner 的正式发布审核必须分开。

## Acceptance Criteria

形成任务和执行记录的状态清单与转换规则；明确每类执行主体的责任和交接边界；明确 MCP Submission 与 Execution Record 的最小关系；明确重试、转交、人工接管、重复提交和幂等语义；明确 TaskNode Owner 审核与 Project Owner 正式批准的边界；明确失败何时必须生成 Mapping Proposal；不引入具体技术实现。
