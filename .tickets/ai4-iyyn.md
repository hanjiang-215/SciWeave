---
id: ai4-iyyn
status: closed
deps: [ai4-gqj3, ai4-2h8c]
links: []
created: 2026-10-20T07:46:47Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, task-agent, ready-for-agent]
---
# 最小 Task Agent 项目组端到端验收

> **形态修订（2026-10-21）：本票的验收对象已改为端侧自持形态，现有验收标准尚未重写，暂不可按此关闭。**
>
> 依据工单「Task Agent 改由研究员端侧自持」。中央侧不再验收 Worker Lease、中央 Gateway 健康聚合和中央容器部署；端侧新增验收端侧网关、订阅器、草稿提交和主体能力校验。修订要点见文末 Notes 的 2026-10-21 条。

## Parent

最小 Task Agent 项目组实现规格（ai4-z3z4）。

## What to build

以认证 MCP 客户端完整验证 Task Agent 项目组的 Owner 命令、调度、Worker、fast-agent、控制、会话恢复和健康行为，并证明本阶段没有引入领域 Buffer 或实际消息队列消费。

## Acceptance Criteria

## Acceptance Criteria

- [ ] 从认证 MCP 接缝验证命令提交、查询、幂等、取消、列表、审核和错误边界。
- [ ] 验证 Worker Lease 串行化、Worker 释放、运行时成功和失败、waiting 恢复、返修及固定会话恢复。
- [ ] 验证 Gateway 重启后读取持久状态和审计，不自动重做 failed 执行。
- [ ] 验证 MCP 与回环 HTTP 健康结果的规定差异，以及未配置 ingest 的明确状态。
- [ ] 运行项目组同步、安装、编译与全部自动化测试；记录命令、结果和遗留风险。
- [ ] 验证未引入领域 Buffer、领域 MCP、实际队列消费或真实模型凭据。

## Notes

**2026-10-21T13:08:58Z**

2026-10-21T21:13:00Z

验收对象变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)：本票原定验收「中央项目组」的端到端行为，包括中央 Gateway 拉起 Worker、共享 SQLite 租约、健康聚合。端侧自持后这些不再属于中央。

新的验收边界需要重写为：

- 研究员电脑上的端侧 Gateway 能接收本机 Owner 的 MCP 命令并完成一次 loop。
- 端侧常驻订阅器能主动连接中央队列，订阅所属 TaskNode 并接收上游交接。
- 端侧 agent 能把结果作为草稿提交到中央草稿箱的对应命名空间。
- 中央侧按主体校验 MCP 能力，越权调用被拒绝且不产生事实写入。
- 不再验收中央侧的 Worker Lease、中央 Gateway 健康聚合、中央容器部署。

本票保持 in_progress，修订前不按现有验收标准关闭。

**2026-10-21T14:14:43Z**

2026-10-21T22:16:00Z

补充变更，依据「Agent 以消息驱动，MCP 只负责返修」(ai4-dhpv)：验收还需覆盖消息驱动语义。

- 首轮执行由上游交接消息或根任务就绪消息触发，不经 MCP 命令。
- MCP 只验收返修、验收、驳回、请求人工接管、观察；不再验收任务提交类工具。
- 验收端侧 agent 与中央服务之间的能力面边界：只能检索自己提交的草稿、只能提交 candidate。

前一条 2026-10-21T21:13:00Z 的验收边界修订仍然有效。

**2026-10-21T14:35:45Z**

2026-10-21T22:40:00Z

## Resolution

本票暂时关闭。原因是验收前置未定：task-agent 的部署位置与方式还没有界定清楚，在此之前验收清单会随形态反复变化。

关闭不等于否定现有成果，两点明确保留：

1. **跑通本身是有意义的结论。** 现有实现已经证明「MCP 客户端 → Gateway → Worker → fast-agent loop → 会话恢复」这条链路能走通。这个验证结果不因部署位置改变而失效。
2. **MCP 提交命令的工作仍然有用。** 返修要求本身也是一条命令，仍需要 `submit_owner_command` 这样的结构化入口。后续可能通过提示词约束 task-agent 与 centre-agent 的能力，让它们只做返修相关的工作，而不是把工具删掉。

未来改进大概率基于现有模板：同构（Gateway + 短生命周期 Worker + 共享 SQLite + 原子租约）保留，变的是部署位置、入口触发方式（消息驱动）和工具用途收窄。

重新开启条件：task-agent 的部署位置与方式确定后，按新形态重写验收标准再开工。原验收标准保留在正文，供追溯。

依据工单：「Task Agent 改由研究员端侧自持」「Agent 以消息驱动，Gateway 的 MCP 只负责返修」。
