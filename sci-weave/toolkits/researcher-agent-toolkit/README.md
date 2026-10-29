# 研究员的 Agent套件

研究员套件导出到显式项目根的 `.sciweave/harness/researcher-agent-toolkit/`。Harness 自行注册技能和 MCP。Task Agent 代码、数据和日志属于该项目实例；Linux systemd 用户服务必须绑定项目根，移动后需显式重绑。Windows 后台服务未验证，不能报告为已安装。配置名称见 `configuration.md`。

`deploy-task-agent/` 含三块：skill（教研究员改 Agent 定义）、服务模板（只负责启动 gateway）、libs（运行时和 fast-agent 卡片样例）。与中央 Centre Agent 不共享源码。详见 [ADR-0002](../../../docs/adr/0002-work-agent-two-codebases.md)。