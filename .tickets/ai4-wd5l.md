---
id: ai4-wd5l
status: closed
deps: [ai4-ufqu]
links: []
created: 2026-10-19T01:14:56Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-kpvp
tags: [wayfinder:grilling]
---
# Task Agent 与审核人协作及返修流程

## Question
明确 Task Agent 与 TaskNode Owner/审核人之间的审核协作通信流程。需要决定结果提交、问题澄清、补充信息、返修、重试、驳回、人工接管和审核通过等消息与状态如何衔接；明确审核协作何时结束，以及何时生成 TaskNode 交接消息。该票不讨论沿依赖边的下游交接本身，也不选择具体通信渠道或 Agent 框架。

## Acceptance Criteria

形成可交给后续规划的 Review Conversation 流程规格：明确交互参与者、消息类型、Buffer/Execution Record 关联、返修循环、审核决定、审计事件和向 TaskNode 交接流程的边界。


## Notes

**2026-10-19T01:28:20Z**

本轮讨论形成的约束：每个审核协作会话只携带该轮消息、上一轮输出和审核信息，不默认注入额外历史上文；初审由 TaskNode Owner 通过自己的 Codex 调用 MCP 发起和完成，普通聊天不构成审核决定；PO 与 Central Agent 参与后续审核，其中 Central Agent 负责结构、依赖、权限和影响范围预审，PO 负责正式发布判断；审核不通过时结束当前执行 loop，返修或重试创建新的执行 loop，不在同一会话中无限循环。后续流程设计依赖 Task Agent 运行时与套件接入方案。

**2026-10-19T04:01:00Z**

Decision captured（2026-10-19）：Task Agent 可经受限 Artifact MCP 为当前 TaskNode/Execution Record 登记 RawArtifact 名片（外部或受控存储定位、来源、哈希、媒体类型、访问状态），并创建绑定本轮执行的候选 Wiki 资源引用/文档草稿；不直接写入正式 Wiki 或 TerminusDB。Execution Submission 引用这些名片与草稿，TaskNode Owner 接纳后才移交 Wiki 领域治理流程。PDF 等资源本体不存入 LLM-Wiki；若后续有合规对象存储，文件可上传至对象存储而 Wiki 仍仅记录其 RawArtifact 名片。

**2026-10-19T04:02:20Z**

Decision captured（2026-10-19）：Task Agent 创建 Execution Submission 时，端侧协作 Buffer 在同一 SQLite 事务中写入提交、审计事件和面向 TaskNode Owner 的通知 outbox。通知服务可通过邮件、Hook 或应用通知提醒，但不构成审核决定。Owner 只能在其已认证的 Codex 中经 Owner MCP 查询待审提交，并写入结构化审核决定。返修决定生成 Owner Command；Gateway 对同一 TaskNode 串行恢复固定 fast-agent-mcp 会话以执行下一轮。

**2026-10-19T04:05:45Z**

Decision captured（2026-10-19，修订审核接纳语义）：Owner 对 Execution Submission 作 accept 后，端侧 Buffer 不仅通知 Central Agent；它以已接纳提交中的候选 Mapping/Wiki 变更为输入，创建对应领域的草稿版本/候选变更，并把领域草稿标识、来源 Submission/Execution Record 与审计证据经 outbox 交给 Central Agent。Central Agent 后续负责候选版本的冲突检查、混合方案与送交 PO；PO 批准正式发布后 TaskNode 才结束，并由该正式化流程原子纳入下游交接消息。端侧流程到领域草稿创建及 Central Agent 通知为止。若一次提交同时提出 Mapping 与 Wiki 改动，必须拆成各自独立领域草稿，不创建跨域 Proposal。

**2026-10-19T04:06:39Z**

Decision captured（2026-10-19）：Owner 的 accept 在端侧 SQLite Buffer 的单一事务中写入审核接纳决定、AuditEvent 和“创建领域草稿”的 outbox 事件。领域适配器以 submission_id + domain 作为幂等键创建 Mapping 或 Wiki 草稿；成功后才经后续 outbox 通知 Central Agent，失败安全重试。该语义保证审核接纳不会因跨库故障丢失草稿创建意图，但不宣称 SQLite 与领域存储具有跨库原子提交。

**2026-10-19T04:08:12Z**

Resolution（2026-10-19）：端侧审核协作流程已收束。1）Gateway 只在所有必需上游 TaskNode 已完成 PO 批准的正式发布、且正式化流程已沿 Dependency Edge 发布正式交接消息后，收集其正式版本引用并启动下游 Task Agent 首轮；候选或仅 Owner 接纳但未正式化的内容不得触发下游。2）每个 TaskNode 固定复用受 Gateway 控制的 fast-agent-mcp Harness 会话，Gateway 串行化调用。3）每轮 Worker 创建不可变 Execution Record 与 Execution Submission；Submission 可引用 RawArtifact 名片和候选领域草稿，不直接改正式领域事实。4）SQLite 为端侧 Buffer 权威状态，Owner 在 Codex 中经 MCP 作 accept/request_revision/reject/request_human_takeover；通知仅为 outbox 提醒，非审核事实。5）request_revision 生成 Owner Command 并恢复同一会话；reject 不自动重试；人工接管停止调度。6）accept 在 SQLite 事务中写审核决定、AuditEvent 及领域草稿创建 outbox；领域适配器以 submission_id + domain 幂等创建独立 Mapping/Wiki 草稿，成功后通知 Central Agent。Central Agent 的冲突/混合/送 PO 及 PO 正式发布不在本票实现范围；PO 正式发布后才结束任务并原子纳入下游交接。7）PDF 等本体不存 Wiki；Task Agent 只登记带定位、来源、哈希、媒体类型和访问状态的 RawArtifact 名片，候选 Wiki 内容在 Owner 接纳后走 Wiki 治理。
