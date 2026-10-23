# 研究员的 Agent套件

研究员把套件 zip 发给自己的 Agent（WorkBuddy、Codex 等），由它安装，平台不在这里启动服务。

`deploy-task-agent/` 含三块：skill（教研究员改 Agent 定义）、服务模板（只负责启动 gateway）、libs（运行时和 fast-agent 卡片样例）。与中央 Centre Agent 不共享源码。详见 [ADR-0002](../../../docs/adr/0002-work-agent-two-codebases.md)。