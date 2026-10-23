# 故障定位

- `unknown_agent`、`unknown_workflow_type`、`cyclic_reference`：修正 Agent 或工作流配置。
- `unknown_mcp_resource`：检查允许列表与标准/本地描述符名称。
- `child_agent_failed`：用假 Agent 重现，确认失败 Agent 和提示输入；不要修改 runtime。
- `final_writer_failed` 或无 `draft_id`：检查最终写入 Agent 的声明和假草稿箱交互。
- 用户服务未运行：执行 hook 或查看 `systemctl --user status`；不要在 harness 关闭时 stop 服务。
- 重复事件：检查唯一 `event_id` 与目标配置，确认没有创建第二个平台执行。
