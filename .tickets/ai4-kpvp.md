---
id: ai4-kpvp
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
# 端侧 Agent 协作与治理分支

厘清研究人员自有 Personal Agent 与平台轻量任务 Agent 的端侧协作方式，以及它们与 Mapping、Wiki、消息协作及审核治理的边界。按用户要求先建立讨论入口，后续再逐步收敛；不预设通用 Agent 产品或运行时技术栈。

## Acceptance Criteria

形成可供后续规划使用的端侧 Agent 角色与协作规格，至少明确 Agent 类型/责任边界、任务执行及提交入口、审核与人工接管关系、与消息协作和套件能力的衔接；具体实现和模型选型另行决策。

## Notes

**2026-10-18T15:39:58Z**

本分支规划变更已推送至 feature/qiyueran，当前提交 622cae7；关联 Pull Request：docs(wayfinder): expand collaboration specification map（https://gitee.com/qi-yueran/ai4science/pulls/8，目标 develop）。本工单保持开放，讨论问题尚未解决。

**2026-10-19T01:15:06Z**

新增前沿分支：将端侧 Agent 通信划分为两类独立决策——（1）TaskNode 交接消息发布与下游触发；（2）Task Agent 与审核人的协作及返修。前者只在任务结果审核通过后沿依赖边发布，后者负责正确性检查、补充和返修；中央 Audit Trace 作为审计轨迹，不视为通信通道。具体流程分别由新建的两个子票讨论。

**2026-10-19T02:20:33Z**

前沿共识（2026-10-19）：端侧 Agent 运行时暂定采用 fast-agent-mcp，并以 TaskNode 模板定义不同任务 Agent；任务执行由外围 Worker/调度程序管理，不由 Task Agent 自行维护跨 loop 历史。Task Agent 输入划分为两条逻辑通道：上游 TaskNode 交接消息与 Task Owner 消息。上游交接消息每个上游只提供一次，先收集必要上游消息并至少执行一轮；在首轮上游驱动执行前不开放 Owner 消息通道。Owner 消息在后续阶段结合 Owner 历史消息和 Agent 处理结果进入处理。两类消息可复用队列基础设施，但触发、优先级、聚合和上下文规则独立。Task Agent -> Owner 暂定采用服务器 Buffer + Codex Hook 主动发现/拉取 + 邮件通知；邮件不构成审核决定，研究员仍通过自己的 Codex 调用 MCP 完成结构化审核。fast-agent-mcp 历史保存、恢复、窗口和压缩机制仍待独立研究。

**2026-10-19T04:08:12Z**

前沿决议：子票“Task Agent 与审核人协作及返修流程”已收束并关闭。端侧执行从正式上游交接启动，经不可变执行提交、Owner Codex MCP 审核、SQLite outbox 领域草稿创建，到 Central Agent 通知为止；任务仅在 PO 正式发布后结束并触发下游交接。详情见 ai4-wd5l 的 Resolution。
