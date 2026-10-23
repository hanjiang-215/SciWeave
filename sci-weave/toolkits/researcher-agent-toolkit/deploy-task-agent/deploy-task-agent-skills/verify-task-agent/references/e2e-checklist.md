# 端到端检查清单

1. 假队列向 subscriber 投递一个 `event_id` 和 `target_id`。
2. subscriber 将消息交给一个 Worker；Worker 获取一个租约并运行配置工作流。
3. Router、Orchestrator、Parallel 或 Agents as Tools 的子 Agent 在同一执行上下文中完成。
4. 最终写入 Agent 调用假草稿箱恰好一次，结果状态为 `completed`，`draft_id` 非空且唯一。
5. 重复投递同一事件保持幂等；失败子 Agent 不写草稿。

推荐命令：`cd runtime && uv run python -m unittest discover -s tests -v`。