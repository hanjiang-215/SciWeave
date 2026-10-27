# Agent 定义参考

必填字段：`identity`、`instruction`、`model`（`name` 也要写，与 `agents:` 下的键名一致）。`allowed_domain_mcps` 只声明该 Agent 必须使用的领域资源；资源名称必须来自标准 `mcp-libs` 或兼容的 `local-mcp-libs`。工作流中的 Agent 名称必须能在定义中解析。

单 agent 文件同样要写在 `agents:` 段下面：

```yaml
agents:
  my-agent:
    name: my-agent
    identity: 我的科研 Agent
    instruction: |
      ...
    model: configure-in-your-own-environment
    allowed_mcp_resources: [research-mapping, draft-buffer]
    resources: []
```

把 `name:` 直接写在顶层是无效的——解析结果是零个定义，runtime 报 `[no_definitions]`。写错字段名则报 `[unknown_field]` 并列出键名。

允许修改：Agent 定义中的身份、指令、模型、引用、工具链接和资源声明。禁止修改：`runtime/src/`、Worker Lease、Gateway、队列消费者和 systemd 服务。凭据只放 `.env`，仓库仅保留 `.env.example`。
