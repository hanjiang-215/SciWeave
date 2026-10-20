# Task Agent Worker 角色

该子项目将由 Gateway 短生命周期启动，运行一次 fast-agent-mcp Worker loop，并经受控进程边界回报退出结果。

当前仅建立独立、可安装的项目骨架；未引入 fast-agent-mcp 依赖，未实现运行时 loop、Buffer 交付或恢复逻辑。
