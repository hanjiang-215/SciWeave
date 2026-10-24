# Buffer

中央草稿箱保存尚未进入领域候选分支的 Research Mapping 路线变更与 LLM-Wiki 文档/引用草稿，由配置的领域审核人进行一审。草稿正文与状态仅保存在一个 TerminusDB 数据库 `sciweave_draft_domain`；`mapping` 与 `wiki` 是命名空间字段，不是独立数据库。服务不会创建候选、写领域正式存储或发起执行。

## 边界与流程

- 使用 `Draft` 与 `NamespaceConfig` 文档，`@key` 为 TerminusDB `Random`；正文 payload 以 JSON 保存。
- 提交时固定 exact TerminusDB Commit。后续修改只影响可编辑草稿，不改变该次审核快照。
- 状态：`drafting → submitted → accepted → promoted`；驳回为 `rejected`，修订创建新的提交身份并保留 `supersedes_draft_id`；未发布草稿可以 `abandoned`。
- 仅提交者可修改草稿；审核人由 `SCIWEAVE_BUFFER_REVIEWERS_JSON` 按命名空间配置。`mark_promoted` 由调用领域 MCP 创建候选的一方显式调用，只记录候选 ID 和 Commit。
    `create_draft`, `update_draft`, `submit_draft`, `review_draft`、`mark_promoted` 接受幂等键；同一键同一请求返回首次结果，不同请求返回冲突。
- stdio MCP transport 不认证调用者。部署方必须通过可信 MCP 宿主注入 `actor_id`（调用工具时的参数字段），并确保调用方不能自行伪造或覆盖它；本服务不信任客户端自行填写的 `actor_id`。当前裸 stdio 入口没有可信身份注入配置，因此工具调用会明确拒绝，必须接入身份注入适配后才能使用写入或审核功能。工具 schema 故意不公开 `actor_id`，由受信任宿主在转发前注入。
- Streamable HTTP MCP transport（配置 `SCIWEAVE_BUFFER_MCP_HOST` 与 `SCIWEAVE_BUFFER_MCP_PORT` 后启用）在 `POST /mcp` 提供同一套 JSON-RPC 工具面，并在 `GET /health` 提供健康检查。HTTP 传输不信任请求体里的 `actor_id`：调用者身份从 `Authorization: Bearer <token>` 解析，按 `SCIWEAVE_BUFFER_MCP_TOKENS_JSON` 映射为 `actor_id` 后由服务端注入工具调用；缺失或未知令牌返回 HTTP 401。启用 HTTP 端点时必须提供令牌映射，不允许匿名端点。

## 配置与运行

复制 `.env.example` 为本机 `.env`，配置 TerminusDB 服务 URL、数据库、认证信息和两个命名空间的审核人。真实 `.env` 不提交。运行配置均通过环境变量注入：

```powershell
uv sync --locked
uv run --env-file .env python src/main.py
```

`SCIWEAVE_BUFFER_TERMINUSDB_URL` 与认证参数必须指向可信 TerminusDB 12.0.8 服务。未设置命名空间审核人时，该命名空间的审核操作拒绝执行。以 stdio MCP transport 运行时，不新增固定监听地址或端口；以 Streamable HTTP transport 运行时，监听地址与端口必须来自环境变量，测试可用回环地址与端口 `0`。

## 验证

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked python -m compileall -q src tests
```

单元测试用内存 Fake Store 覆盖幂等、固定提交、namespace 隔离、审核权限、状态转移、候选标识回写、MCP tool dispatch 和 Streamable HTTP 传输（回环地址与临时端口 `0`，覆盖 Bearer 认证、身份注入、越权拒绝、非法路径/方法、畸形 JSON 和配置校验）。真实 TerminusDB 集成测试使用进程环境变量配置的 12.0.8 服务与临时数据库（测试自动建库、用例结束后删除），不得将真实凭据或固定端口写入仓库：

```powershell
$env:SCIWEAVE_RUN_TERMINUSDB_INTEGRATION="1"
$env:SCIWEAVE_BUFFER_TERMINUSDB_URL="http://127.0.0.1:6363"   # 或复用 SCIWEAVE_WIKI_* 变量
$env:SCIWEAVE_BUFFER_TERMINUSDB_DATABASE="sciweave_buffer_it" # 仅作临时库前缀
uv run --locked python -m unittest tests/test_terminus_integration.py -v
```

## 依赖与许可

业务代码只依赖 Python 标准库；不新增 TerminusDB SDK 或 MCP SDK。PEP 517 构建使用 PyPI `setuptools==80.9.0`（MIT），固定在 `pyproject.toml`/`uv.lock`，用途仅为子项目 editable build。安装与验证命令如上。
