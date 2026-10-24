---
id: ai4-emfn
status: closed
deps: []
links: []
created: 2026-10-24T03:02:48Z
type: chore
priority: 2
assignee: hanjiang
parent: ai4-xup8
tags: [toolkit, mcp, runtime, config]
---
# 对齐套件标准 MCP 卡片与领域管理 MCP 真实工具面

researcher-agent-toolkit/deploy-task-agent/libs/mcp-libs 三张标准卡片（draft-buffer/research-mapping/research-wiki）的工具面、环境变量与 transport/endpoint 声明仍为早期占位，与实际领域管理 MCP 和草稿箱服务不一致：卡片只声明 1 个虚构工具（draft_box_write/research_map_search/llm_wiki_lookup），真实服务各暴露 7-8 个工具；卡片未声明 transport 与 endpoint.url_env，runtime 无法推导连接方式；example-fast-agent.yaml 引用的资源名（research-map-read 等）与卡片 name 不匹配会导致 unknown_mcp_resource。本票将卡片对齐到真实工具面并验证 runtime 加载。关联 ai4-w73z（对外接口）、ai4-za77（套件）。

## Acceptance Criteria

- [x] 三张卡片 tools 与真实服务 TOOL_DEFINITIONS/call_tool 一一对应（draft-buffer 7 工具、research-mapping 7 工具、research-wiki 8 工具），输入参数一致
- [x] 卡片声明 transport=streamable-http 与 endpoint.url_env，environment 使用 .env.example 既有变量名
- [x] example-fast-agent.yaml 的 allowed_domain_mcps 资源名与卡片 name 一致
- [x] runtime 能加载标准 mcp-libs 目录，catalog 输出与真实服务工具面一致；runtime 全量测试通过

## Notes

**2026-10-24 实现与验证（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

提交 `5f3f60f`。改动：

- `libs/mcp-libs/draft-buffer/mcp.json`：占位单工具 `draft_box_write` 替换为 buffer 真实 7 工具（`create_draft`/`update_draft`/`submit_draft`/`list_drafts`/`read_draft`/`review_draft`/`mark_promoted`），输入 schema 取自 `draft_buffer/main.py` 的 `_tool_definitions`。
- `libs/mcp-libs/research-mapping/mcp.json`：占位 `research_map_search` 替换为 7 个管理工具（`get_formal_mapping`…`reconcile_formalization`），输入 schema 与 `research_mapping/management.py` 的 `TOOL_DEFINITIONS` 一致。
- `libs/mcp-libs/research-wiki/mcp.json`：占位 `llm_wiki_lookup` 替换为 8 个管理工具（`get_formal_wiki`…`reconcile_wiki_formalization`），同上对齐。
- 三张卡片补 `transport: "streamable-http"` 与 `endpoint.url_env`（分别指向 `DRAFT_BUFFER_MCP_URL`、`RESEARCH_MAPPING_MCP_URL`、`LLM_WIKI_MCP_URL`），满足 runtime `mcp_resources.py` 对 streamable-http 卡片的 `invalid_endpoint` 校验；`environment` 保持与套件 `.env.example` 同名。
- `agent-definitions/agents/example-fast-agent.yaml`：`allowed_domain_mcps` 从 `research-map-read`/`research-wiki-read`/`draft-buffer-write` 改为卡片名 `research-mapping`/`research-wiki`/`draft-buffer`，消除 `unknown_mcp_resource`。
- `deploy-task-agent-skills/configure-mcp/references/mcp-resources.md`：从"只读映射/只读背景"更新为真实能力面并说明权限由服务端档位裁决。
- 新增 `runtime/tests/test_standard_mcp_cards.py`：加载真实 `libs/mcp-libs` 目录，断言三张卡片的 transport/endpoint/environment 与工具集等于真实服务工具面。

验证（`deploy-task-agent/runtime`）：

- `uv run --locked python -m unittest discover -s tests -v`：18 项全部通过（新增 2 项卡片测试）。
- `uv run --locked python -m compileall -q src tests`：通过（退出码 0）。
- `git diff --check`：通过。

边界：本票只改套件侧描述资源与示例，不动领域服务、草稿箱服务实现，也不改 Frank Qi 名下工单正文。真实 MCP client 连接验证与端到端演示链路在 `ai4-aaff` 侧另做。


