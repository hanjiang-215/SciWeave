---
id: ai4-w4su
status: closed
deps: [ai4-ujvn]
links: []
created: 2026-10-23T16:28:07Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-ujvn
tags: [implementation, centre-control, registery, mcp, audit, ready-for-agent]
---
# 实现 Registry 登记与查询 MCP

实现 Registry 登记事实与查询 MCP 的端到端垂直切片：登记 Principal、Workflow Agent、Agent Instance 和通知联系人，支持状态标记/恢复、幂等、权限边界、共享访问留痕和健康检查。Registry 不参与 TaskNode 鉴权，不保存 executor_refs 或 TaskNode 关系。

## Design

复用共享 audit-trail 记录所有 MCP 访问。使用独立 Python 子项目、标准库 sqlite3、官方 Python `mcp` SDK/`FastMCP`、uv 和环境变量配置；登记事实与访问账本分开保存。实现 register_principal、register_workflow_agent、register_agent_instance、get_principal_contact、get_agent_registration、health。MCP 使用标准 Streamable HTTP 传输；健康探针保留独立 HTTP `/health`。支持 active/disabled、active/retired、starting/online/offline/revoked 状态变更，不提供物理删除。研究员只能操作自己持有的 endpoint Agent，Project Owner 管理 Principal/Agent，Centre 服务按最小读取面查询，email-service 通过 RecipientResolver 只读联系人。

## Acceptance Criteria

- [x] 符合子项目规范，提供 pyproject.toml、uv.lock、.env.example、src/main.py、src/ 和 tests/
- [x] 认证 MCP 工具完成 Principal、Workflow Agent、Agent Instance 登记与查询；必须使用官方 Python mcp SDK/标准 FastMCP，不得以自写 JSON-RPC 兼容层替代
- [x] MCP 使用 Streamable HTTP，健康检查提供独立 HTTP `/health`，并验证 `tools/list`/`tools/call` 行为
- [x] 支持状态标记/恢复、历史保留和多实例，同一 idempotency_key 幂等，冲突返回稳定错误
- [x] get_principal_contact 返回当前有效联系人和稳定的缺失/禁用/不可用错误
- [x] Registry 不保存 executor_refs、TaskNode 集合、授权清单、凭据或主机地址
- [x] 所有 MCP 访问通过 shared audit-trail 留痕，登记事实与访问账本分开
- [x] 研究员、Project Owner、Centre 服务和 email-service 的工具级开放面有行为测试
- [x] health 提供安全的服务/存储状态，失败不修改正式 Map
- [x] 使用临时 SQLite 和 Fake audit/调用边界完成测试，不依赖真实凭据或固定端口
- [x] 完成 uv sync、测试、compileall、README 和验证证据回写本票 Notes


## Notes

**2026-10-25T07:57:00Z（收尾验收，hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

全部 11 条验收已勾选，本票关闭。收尾时在 Windows 复跑 `uv run --env-file .env.example pytest -q`（14 passed）与 `compileall` 通过时，修复了一处 Windows 特有的测试问题：

- `tests/test_http.py::test_audit_storage_failure_makes_both_health_checks_unavailable` 原实现用 `Path.write_bytes` 覆盖 `audit.sqlite` 及其 `-wal`/`-shm` sidecar 模拟存储损坏。审计库以 WAL 模式打开，`-shm` 文件被运行中 server 的 SQLite 连接独占，Windows 上 `write_bytes` 抛 `OSError: [Errno 22] Invalid argument`，测试失败（Linux 不受影响）。
- 改为通过同进程的第二个 SQLite 连接对同一文件 `DROP TABLE audit_call`，server 持有连接下一次 `SELECT 1 FROM audit_call` 即抛 `no such table`，`_storage_ready` 判 false，两个 health 入口（HTTP 503 + MCP `registry_unavailable`）行为断言不变，且不改正式 Map 的断言保持。
- 实验确认仅覆盖主文件不足以触发失败：WAL 连接持缓存仍可查询；drop 表方案跨平台稳定。产品代码未改动，只改了测试的损坏模拟方式。

验证命令与结果：`uv run --env-file .env.example pytest -q` → 14 passed；`uv run --env-file .env.example python -m compileall -q src tests` → 通过。

**2026-10-25T06:58:36Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T06:58:36Z。

**2026-10-24T01:27:21Z**

实现完成（2026-10-24）：在 `sci-weave/centre-control/registry` 建立独立 Python 子项目，提供认证 JSON-RPC/MCP 兼容入口与 HTTP health。实现 Principal、Workflow Agent、Agent Instance 登记、状态更新/恢复、联系人查询、Agent 查询、幂等记录、稳定错误码和共享 audit-trail 接入。登记事实与访问账本分开保存，不保存 executor_refs、TaskNode 关系、授权清单或凭据。目录从历史 `registery` 迁移为标准拼写 `registry`。

验证：在 registry 子项目执行 `uv sync --dev`；`uv run --env-file .env.example pytest -q`，5 passed；`uv run --env-file .env.example python -m compileall -q src tests` 通过。根仓库执行 ticket index check、`git diff --check`、`fer dep cycle` 均通过。测试覆盖联系人查询、研究员自有 endpoint Agent 权限、幂等/多实例、HTTP MCP 鉴权和健康检查。

- MCP 服务使用官方 Python `mcp` SDK（PyPI 包 `mcp`，实现 FastMCP 与 Streamable HTTP）；公共健康端点复用其 Starlette ASGI app，因此 `mcp` 与 `starlette` 都作为运行时依赖在 `pyproject.toml` 中声明。`mcp` 限定 `>=1.30,<2`，`starlette` 限定 `>=0.27,<2`；两者采用 MIT 许可证。来源：<https://github.com/modelcontextprotocol/python-sdk> 与 <https://pypi.org/project/mcp/>、<https://pypi.org/project/starlette/>。安装：`uv sync --dev`；验证：`uv run --env-file .env.example pytest -q`、`uv run --env-file .env.example python -m compileall -q src tests`。

**2026-10-24T03:07:30Z**

更正上一则 Notes：Registry 不再使用自写 JSON-RPC 兼容层。MCP 入口改为官方 FastMCP 的 Streamable HTTP（`/mcp`），独立健康探针仍是 HTTP `GET /health`。调用身份只来自 `SCIWEAVE_REGISTRY_TOKENS_JSON` 中的 bearer token，区分 Project Owner、研究员、Centre 服务（`service_role=centre`）和 email-service（`service_role=email`）。登记保持幂等，冲突返回 `idempotency_conflict`；主体或实例身份冲突返回 `agent_owner_conflict` / `instance_identity_conflict`。状态标记和恢复追加 `status_event`，不物理删除。联系人查询返回 `principal_not_found`、`contact_missing`、`contact_disabled`。写调用在 audit-trail 上 fail-closed，读调用在审计库不可用时 fail-open。

验证：在 `sci-weave/centre-control/registry` 执行 `uv run --env-file .env.example pytest -q`，5 passed；`uv run --env-file .env.example python -m compileall -q src tests` 通过；仓库根目录 `git diff --check` 通过。测试通过官方 MCP 客户端验证 `tools/list`、`tools/call`、未认证 401、四类调用方的工具开放面，以及登记库与 audit 库分离。

**2026-10-24T03:27:37Z**

测试改到认证后的 MCP 接缝，删掉直接打在 `RegistryService` 上的 `tests/test_registry.py`。`tests/test_http.py` 用官方 MCP 客户端和临时端口覆盖：工具清单、未认证 401、公开 `/health`、联系人缺失/禁用/版本、研究员只能登记自己的 endpoint Agent、Centre 与 email-service 的读写面、实例状态历史与恢复、幂等重放和冲突、身份冲突、审计账本不含联系人正文、审计库不可用时写入失败而联系人读取仍成功、登记库损坏时 health 与联系人查询返回不可用且不改正式 Map。

健康检查原先只执行 `SELECT 1`，库文件损坏仍返回 ready。现改为读取 `principal` 与 `audit_call`，存储失败才返回不可用。

验证：在 `sci-weave/centre-control/registry` 执行 `uv run --env-file .env.example pytest -q`，11 passed；`uv run --env-file .env.example python -m compileall -q src tests` 通过。

**2026-10-24T03:55:40Z**

按审查修复：省略的 `contact_email` 和 `last_seen_at` 在更新时保留原值；去掉规格没有的 `deployment_description` 和 health 的 `api_version`。审计库改为 `SCIWEAVE_AUDIT_SQLITE_PATH`，启动时用 `open_connection` 打开并建表，失败则不起服务；写调用的 `begin_call`/`finish_call` 与业务在同一把锁里，失败不执行业务，读调用用 `record_attempted`，失败只告警。MCP `health` 与 `GET /health` 都检查 `principal` 和 `audit_call`。`SCIWEAVE_REGISTRY_HOST` 和 `SCIWEAVE_REGISTRY_PORT` 改为必填，源码不再默认地址或端口。

- `sciweave-audit-trail`：path 依赖 `../shared/audit-trail`，仓库自有代码，记录 MCP 访问账本。安装：`uv sync --dev`。
- `pytest`（`>=8,<9`，MIT，<https://github.com/pytest-dev/pytest>）：开发依赖，跑测试。
- `httpx`（`>=0.28,<1`，BSD-3-Clause，<https://github.com/encode/httpx>）和 `uvicorn`（`>=0.30,<1`，BSD-3-Clause，<https://github.com/encode/uvicorn>）：开发依赖。测试用官方 MCP 客户端和 ASGI 服务，不再只靠 `mcp` 的传递依赖。

验证：在 `sci-weave/centre-control/registry` 执行 `uv add --dev "httpx>=0.28,<1" "uvicorn>=0.30,<1"`；`uv run --env-file .env.example pytest -q`，14 passed；`uv run --env-file .env.example python -m compileall -q src tests` 通过。
