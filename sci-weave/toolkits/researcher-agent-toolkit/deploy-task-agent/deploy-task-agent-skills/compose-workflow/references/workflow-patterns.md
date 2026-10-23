# 工作流模式

- `Router`：入口返回 `route:<子Agent>`，只执行选中的分支。
- `Orchestrator`：依次调用子 Agent，再由汇总器合并结果。
- `Parallel`：并发调用相互独立的子 Agent，再交给最终写入 Agent。
- `Agents as Tools`：入口 Agent 只获得其定义中声明的工具子集。

四种模式都由一个 Worker 执行；最终写入 Agent 只调用一次草稿箱，因此一次平台执行只有一个 `draft_id`。未知 Agent、循环工具引用和无效路由应在配置加载或验证时失败。