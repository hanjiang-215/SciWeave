---
name: sciweave-mcp-bridge
description: 以 skill 形式封装到 SciWeave 中央管理 MCP 的 JSON-RPC over HTTP 调用（路径 B，ai4-v869）。当平台不支持原生外部 MCP server 时启用。
---

# SciWeave 中央管理 MCP 桥（路径 B）

把中央 Research Mapping 管理 MCP 的 `get_formal_mapping` / `submit_candidate` / `preview_candidate` 等只读与候选提交工具封装为 HTTP JSON-RPC 调用。行为与路径 A（原生 MCP）等价：agent 用本 skill 完成调用，不声称平台原生支持 MCP。

## 常量（由用户配置，不得硬编码真实值）

- `<ENDPOINT>`：中央管理 MCP 地址（形如 `https://host/mcp`）。
- `<TOKEN>`：Bearer 令牌，仅授予 `read` + `candidate_submit` 能力档；不授予 `candidate_review` / `formalize`。

## 调用模板

### initialize（每次会话一次）

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"sciencepal-bridge","version":"0.1.0"}}}
```

### tools/list

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

### 工具调用

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"<TOOL>","arguments":{...}}}
```

## 约束

- 工具结果只在 MCP `content` 的 JSON 文本对象内，原样返回。
- 业务失败以 `isError: true` + JSON 文本 `{ "error": { "code", "message" } }` 表达；错误码含 `forbidden`、`base_revision_missing`、`no_such_revision`、`unavailable` 等。
- 不允许调用 `candidate_review` / `formalize` / `record_review`；agent 实际遇到这些工具时应报告「无权，需人工处理」而不是猜测执行。
- 每次调用应记录操作者与审计意图；审计由中央接口层账本负责，桥本身不造审计副本。