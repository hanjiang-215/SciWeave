---
id: ai4-w4su
status: closed
deps: [ai4-ujvn]
links: []
created: 2026-10-23T16:28:07Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-ujvn
tags: [implementation, centre-control, registery, mcp, audit, ready-for-agent]
---
# 实现 Registry 登记与查询 MCP

实现 Registry 登记事实与查询 MCP 的端到端垂直切片：登记 Principal、Workflow Agent、Agent Instance 和通知联系人，支持状态标记/恢复、幂等、权限边界、共享访问留痕和健康检查。Registry 不参与 TaskNode 鉴权，不保存 executor_refs 或 TaskNode 关系。

## Design

复用共享 audit-trail 记录所有 MCP 访问。使用独立 Python 子项目、标准库 sqlite3、uv 和环境变量配置；登记事实与访问账本分开保存。实现 register_principal、register_workflow_agent、register_agent_instance、get_principal_contact、get_agent_registration、health。支持 active/disabled、active/retired、starting/online/offline/revoked 状态变更，不提供物理删除。研究员只能操作自己持有的 endpoint Agent，Project Owner 管理 Principal/Agent，Centre 服务按最小读取面查询，email-service 通过 RecipientResolver 只读联系人。

## Acceptance Criteria

- 符合子项目规范，提供 pyproject.toml、uv.lock、.env.example、src/main.py、src/ 和 tests/\n- 认证 MCP 工具完成 Principal、Workflow Agent、Agent Instance 登记与查询\n- 支持状态标记/恢复、历史保留和多实例，同一 idempotency_key 幂等，冲突返回稳定错误\n- get_principal_contact 返回当前有效联系人和稳定的缺失/禁用/不可用错误\n- Registry 不保存 executor_refs、TaskNode 集合、授权清单、凭据或主机地址\n- 所有 MCP 访问通过 shared audit-trail 留痕，登记事实与访问账本分开\n- 研究员、Project Owner、Centre 服务和 email-service 的工具级开放面有行为测试\n- health 提供安全的服务/存储状态，失败不修改正式 Map\n- 使用临时 SQLite 和 Fake audit/调用边界完成测试，不依赖真实凭据或固定端口\n- 完成 uv sync、测试、compileall、README 和验证证据回写本票 Notes


## Notes

**2026-10-24T01:27:21Z**

实现完成（2026-10-24）：在 `sci-weave/centre-control/registry` 建立独立 Python 子项目，提供认证 JSON-RPC/MCP 兼容入口与 HTTP health。实现 Principal、Workflow Agent、Agent Instance 登记、状态更新/恢复、联系人查询、Agent 查询、幂等记录、稳定错误码和共享 audit-trail 接入。登记事实与访问账本分开保存，不保存 executor_refs、TaskNode 关系、授权清单或凭据。目录从历史 `registery` 迁移为标准拼写 `registry`。

验证：在 registry 子项目执行 `uv sync --dev`；`uv run --env-file .env.example pytest -q`，5 passed；`uv run --env-file .env.example python -m compileall -q src tests` 通过。根仓库执行 ticket index check、`git diff --check`、`fer dep cycle` 均通过。测试覆盖联系人查询、研究员自有 endpoint Agent 权限、幂等/多实例、HTTP MCP 鉴权和健康检查。
