---
id: ai4-glmy
status: closed
deps: []
links: []
created: 2026-10-19T02:16:19Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-ufqu
tags: [wayfinder:research]
---
# fast-agent-mcp 历史保存、恢复与上下文隔离验证

## Question
基于 drafts/osp 中下载的 fast-agent 源码，验证其历史保存、恢复、历史窗口、上下文压缩、独立 Session 和 use_history 开关的实际行为，特别关注外围 Worker 为不同 TaskNode、Execution Record、Owner 消息 loop 和上游交接 loop 管理历史时的隔离、恢复和审计可控性。研究结果用于决定平台采用 fast-agent-mcp 的受控 Session 历史，还是由外围程序完全关闭运行时历史并显式拼装上下文。

## Acceptance Criteria

形成可支撑运行时决策的源码验证结论：记录历史开关、Session 标识与存储位置、Worker 隔离方式、恢复行为、窗口/压缩行为、审计可见性和与平台显式上下文共存时的风险；不修改主项目依赖，不实现产品代码。


## Notes

**2026-10-19T03:10:32Z**

2026-10-19：按负责人指示启动上下文管理专项验证。目标优先判断 fast-agent-mcp 的历史、Session 隔离、恢复与压缩能力能否被平台受控复用；仅在证据证明无法满足隔离、审计或恢复要求时才考虑平台自行实现。

**2026-10-19T03:40:53Z**

Resolution（2026-10-19）：首版受控复用 fast-agent-mcp Harness 会话历史，不自建模型对话记忆或 SQLite 会话注册表。Gateway 为每个 TaskNode 生成并控制稳定 session_id；同一 TaskNode 的上游驱动执行、Owner 补充、返修与重试均恢复该会话。不同 TaskNode、租户和并行分支不得共用会话。平台/Gateway 仍负责认证授权、会话键映射、同会话串行调度、跨任务材料筛选、保留删除与审计索引。采用 connection 范围和持久 home，禁止 shared 与 request 范围作为连续任务会话；生产默认关闭自动 compaction，待按模型验证后再开启。证据与复现命令见 docs/fast-agent-mcp上下文管理调研.md。
