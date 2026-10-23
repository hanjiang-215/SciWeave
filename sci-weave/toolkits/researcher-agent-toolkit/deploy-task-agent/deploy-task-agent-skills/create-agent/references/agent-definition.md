# Agent 定义参考

必填字段：`name`、`instruction`、`model`。`allowed_domain_mcps` 只声明该 Agent 必须使用的领域资源；资源名称必须来自标准 `mcp-libs` 或兼容的 `local-mcp-libs`。工作流中的 Agent 名称必须能在定义中解析。

允许修改：Agent 定义中的身份、指令、模型、引用、工具链接和资源声明。禁止修改：`runtime/src/`、Worker Lease、Gateway、队列消费者和 systemd 服务。凭据只放 `.env`，仓库仅保留 `.env.example`。
