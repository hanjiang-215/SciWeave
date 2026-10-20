# 工单模块：Gateway 与执行运行时

> 由 `ticket-index` 技能生成，请勿手工编辑。总览：[索引](../INDEX.md) · 归属与简介：[index.toml](../index.toml)

**范围**：Gateway MVP、Owner MCP、状态与端口、Worker 调度、fast-agent 适配与验收

**统计**：共 16 张 · 活跃 8（open 8 / in_progress 0） · 已关闭 8 · 地图 1

## 工单层级

- [ai4-yyy9](../../../.tickets/ai4-yyy9.md) **Gateway 与最小 fast-agent 执行闭环规格地图** — 规划最小 Gateway 与 fast-agent 执行闭环，收敛 Owner 请求、会话、执行、审计和运行时边界 `epic` `map` `P1` `open` `Frank Qi`
  - [ai4-z3z4](../../../.tickets/ai4-z3z4.md) **最小 Task Agent 项目组实现规格** — 汇总三角色项目组、共享 SQLite、MCP v1、调度和运行时的整体可实施规格 `feature` `P1` `open` `Frank Qi`
    - [ai4-2h8c](../../../.tickets/ai4-2h8c.md) **fast-agent Runtime Adapter 与固定会话恢复** — 将 fast-agent 接入短生命周期 Worker，验证固定会话、持久 home 与恢复执行 `feature` `P1` `open` `Frank Qi` · 阻塞于 [ai4-m96w](../../../.tickets/ai4-m96w.md)（open）
    - [ai4-gqj3](../../../.tickets/ai4-gqj3.md) **ExecutionRecord 控制、审核与恢复 MCP 工具** — 通过 MCP 提供取消、待处理列表、审核和暂停恢复，并保持 ExecutionRecord 审计关联 `feature` `P1` `open` `Frank Qi` · 阻塞于 [ai4-m96w](../../../.tickets/ai4-m96w.md)（open）
    - [ai4-iyyn](../../../.tickets/ai4-iyyn.md) **最小 Task Agent 项目组端到端验收** — 从认证 MCP 客户端端到端验收 Task Agent 调度、运行时、控制工具与健康边界 `feature` `P1` `open` `Frank Qi` · 阻塞于 [ai4-gqj3](../../../.tickets/ai4-gqj3.md)（open）、[ai4-2h8c](../../../.tickets/ai4-2h8c.md)（open）
    - [ai4-m96w](../../../.tickets/ai4-m96w.md) **带 Worker Lease 的本地调度与测试运行时** — 以共享 SQLite Worker Lease 驱动本地短生命周期 Worker，并验证同节点串行化 `feature` `P1` `open` `Frank Qi` · 阻塞于 [ai4-p19z](../../../.tickets/ai4-p19z.md)（open）
    - [ai4-p19z](../../../.tickets/ai4-p19z.md) **MCP v1 命令闭环与共享执行持久化** — 通过 MCP v1 打通 Caller、命令留痕、执行持久化、幂等和最小健康的首个实现闭环 `feature` `P1` `open` `Frank Qi`
    - [ai4-0nuq](../../../.tickets/ai4-0nuq.md) **Gateway 健康检查与 Owner Command 基础闭环** — 打通命令提交、幂等键、SQLite 状态持久化及执行与健康查询的第一条垂直路径 `feature` `P1` `closed` `Frank Qi`
    - [ai4-b8vm](../../../.tickets/ai4-b8vm.md) **本地 Worker Scheduler 与 Runtime Adapter** — 实现按 TaskNode 串行的短生命周期 Worker 调度、运行时调用、失败与取消 `feature` `P1` `closed` `Frank Qi`
    - [ai4-o806](../../../.tickets/ai4-o806.md) **最小 fast-agent Runtime Adapter 与固定会话恢复** — 用 passthrough 模型跑通一次 Agent loop，并为 TaskNode 固定会话与持久 home `feature` `P1` `closed` `Frank Qi`
    - [ai4-vqkn](../../../.tickets/ai4-vqkn.md) **Owner Command 幂等与 Execution 状态持久化** — 保证幂等键唯一对应一次执行，且执行状态和审计在 Gateway 重启后仍可读 `feature` `P1` `closed` `Frank Qi`
    - [ai4-wdvf](../../../.tickets/ai4-wdvf.md) **Gateway MVP 与最小 fast-agent 集成验收** — 通过 MCP 公共接口验收命令、幂等、Worker、fast-agent、失败、取消和会话恢复闭环 `feature` `P1` `closed` `Frank Qi`
  - [ai4-gq0k](../../../.tickets/ai4-gq0k.md) **Gateway MVP 状态模型与端口边界** — 确定 MVP 的 Owner 入口、SQLite 持久化、本地调度、运行时适配和端口边界 `epic` `P1` `closed` `Frank Qi`
  - [ai4-yvh2](../../../.tickets/ai4-yvh2.md) **执行与接纳状态机融合及 Owner 审核工具边界** — 统一 Worker 执行、暂停恢复、Owner 审核与两类触发的状态机及 MCP 工具契约 `grilling` `P1` `closed` `Frank Qi`
  - [ai4-zfz9](../../../.tickets/ai4-zfz9.md) **Gateway MCP 对外协议版本、鉴权与错误契约** — 确定最小 MCP v1 的版本、Bearer 调用者校验、工具错误边界与命令留痕语义 `task` `P1` `closed` `Frank Qi`
- [ai4-353s](../../../.tickets/ai4-353s.md) **Task Owner 通道（MCP）与上游交接队列物理隔离** — 确定 Owner MCP、上游交接队列、常驻 Gateway 与短生命周期 Worker 的物理隔离 `epic` `P1` `open` `Frank Qi` · 上级 [ai4-ufqu](../../../.tickets/ai4-ufqu.md)（Agent 与消息协作）
