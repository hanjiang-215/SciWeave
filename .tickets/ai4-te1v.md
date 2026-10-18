---
id: ai4-te1v
status: open
deps: []
links: []
created: 2026-10-18T15:18:52Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-xup8
tags: [wayfinder:grilling]
---
# 消息队列协作模型分支

为 SciWeave 多人、多 Agent 协作厘清消息模型与交接语义；已有 humans/dev/消息队列协作设计.md 作为讨论起点。当前只开工单，不选消息队列产品或协议，也不进入实现。

## Acceptance Criteria

形成可交给后续实现规划的消息协作领域规格，至少明确 topic/订阅、消息类型与载荷边界、接收者交接/阻塞完成语义、前置任务条件及失败/超时处理；具体基础设施选型另行决策。

## Notes

**2026-10-18T15:38:23Z**

补充记录：将 `humans/dev/消息队列协作设计.md` 的现有讨论输入纳入本工单；草案目前尚未批准，以下均为待讨论方向，不代表产品语义或基础设施选型已经确定。

初始方向：
- 消息协作面向多人、多 Agent 的任务交接，不只是后台任务派发。
- TaskNode 可作为 topic，下游节点可监听前置节点消息；一个节点可以有多个监听者，所有监听者都应收到消息。
- 消息应结构化并承载进度等协作载荷；详细材料通过 Wiki 或 Buffer 链接访问，不在消息中放置大段正文。
- 端侧 Agent 可通过专用 tools 和 MCP 通知审核人；审核人使用自己的 harness 检查 Buffer 修改并通知 Project Owner。涉及多个 Proposal 或候选分支时，Central Agent 预审是独立步骤。
- 人工交接只有在接收者完成工作并通过自己的 harness 发送后续消息后才算完成；仅收到或确认通知不算完成。接收者发送后续消息前处于阻塞状态，上游节点发出交接消息后解除自身阻塞。
- 若不创建后续 TaskNode，仍应向 Project Owner 发送汇总结果。多个接收者可以分别直接向下游通知，不要求由单一负责人统一汇总。

开放问题：
- 下游节点应等待所有前置节点消息，还是按 Dependency Edge 激活条件决定。
- 消息类型如何划分（例如进度更新与完成交接），哪些类型会触发下游工作。
- 多个监听者的独立工作、阻塞状态、完成条件和分支之间如何关联。
- 人类接收者延迟或不可用时如何提醒、转交或人工解除；超时本身不能代表工作完成。
- 专用 MCP/tools 的职责，以及 Central Agent 预审如何衔接 TaskNode 消息交接。
- 载荷必填字段、消息版本、Wiki/Buffer 链接、topic 订阅范围、订阅者变更和接收者快照规则。
- 产品层消息语义与最终队列基础设施、协议、存储及部署方案的边界。

本讨论暂不包含消息队列产品、协议、数据库或云服务选型，最终载荷结构或状态机，代码实现、依赖新增和部署设计。

**2026-10-18T15:39:58Z**

消息队列草案已纳入本工单讨论备注；相关规划变更已推送至 feature/qiyueran，当前提交 622cae7；关联 Pull Request：docs(wayfinder): expand collaboration specification map（https://gitee.com/qi-yueran/ai4science/pulls/8，目标 develop）。本工单保持开放。
