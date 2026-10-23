# Centre Agents

中央服务器上的协调 Agent。它做调度和提案预审，不代替负责人做最终批准。

本目录是独立项目，尚未实现。它只放 Centre Agent：中央服务器上的预审服务，Agent 定义写死。不在这里托管 Task Agent。

源码与 `sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent` 各写一份，行为对齐「最小 Work Agent 实现规格」。现有 `sci-weave/task-agent/` 以后用 `git mv` 作为本目录的起点。详见 [ADR-0002](../../../docs/adr/0002-work-agent-two-codebases.md)。
