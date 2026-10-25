---
id: ai4-cl3t
status: closed
deps: [ai4-sxpw]
links: [ai4-s2nb]
created: 2026-10-23T05:18:40Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-o2n3
tags: [implementation, task-agent, mcp, custom-service, uv, local-mcp-libs]
---
# 自定义 MCP 服务目录与 local-mcp-libs 注册机制

在 deploy-task-agent 下增加自定义 MCP 服务实现目录。自定义 MCP 服务作为独立 Python/uv 子项目，使用 src/main.py、pyproject.toml、uv.lock 和 tests；local-mcp-libs 继续保存 MCP 服务卡片/连接注册、工具目录和权限元数据。runtime 根据注册卡片连接或启动已批准的服务，不把服务实现混入 libs 配置资源。

## Design

1. 在 deploy-task-agent/custom-mcp/ 下建立自定义服务目录和可复制的最小服务模板。
2. 服务按仓库 Python 子项目规范由 uv 管理，启动命令使用 uv run --env-file .env ...。
3. 在 libs/local-mcp-libs/ 中定义服务注册卡片协议，至少支持服务名、版本、传输方式、环境变量映射、启动入口、工具和访问能力。
4. 验证 runtime 能读取注册卡片并拒绝未知服务、越权工具、硬编码凭据和不安全路径；不允许卡片内嵌任意 Python 代码。
5. 先实现本地 stdio 或 Streamable HTTP 其中一条明确路径，另一条保留协议扩展点。

## Acceptance Criteria

- [x] deploy-task-agent/custom-mcp/ 下存在遵守目录规范的可运行自定义 MCP 服务样例/模板。
- [x] 自定义服务具有独立 pyproject.toml、uv.lock、src/main.py 和 tests。
- [x] local-mcp-libs 提供可校验的服务注册卡片和工具注册示例。
- [x] 注册卡片可表达 uv 启动或环境变量 URL 连接方式，但不保存真实令牌、不内嵌 Python 代码。
- [x] runtime 能解析注册卡片并生成 MCP 连接配置，拒绝未知服务、未知工具和不符合权限边界的配置。
- [x] 自定义服务可通过 uv 命令完成最小启动或协议握手验证。
- [x] 依赖通过自定义服务 pyproject.toml/uv.lock 声明，记录来源、用途、许可证/限制和验证命令。
- [x] 不修改现有 ExecutionRecord、Worker Lease 和服务模板接口；相关测试及 git diff --check 通过。


## Notes

**2026-10-25T08:10:00Z（收尾验收，hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

全部 8 条验收已勾选，本票关闭。收尾时补充了 runtime 对注册卡片安全校验的自动化测试覆盖，此前验收第 6 条（拒绝未知服务、未知工具、越权配置）只有实现无测试：

- 新增 `runtime/tests/test_mcp_service_cards.py`（11 个用例）：接受安全 stdio 卡片、拒绝未知传输（`invalid_transport`）、拒绝非 uv 可执行（`unsafe_startup`）、拒绝任意启动参数、拒绝缺 `project_dir_env`、拒绝 HTTP 卡片携带 startup、拒绝 HTTP 无 `url_env`（`invalid_endpoint`）、拒绝重复工具（`invalid_resource`）、未知服务稳定错误码（`unknown_resource`）、本地主版本不兼容（`incompatible_version`）、两本地源同名冲突（`resource_conflict`）。全部使用 `tempfile` 临时卡片，不依赖真实令牌或端口。
- 验证：`uv run python -m unittest discover -s tests` → 29 passed（原 18 + 新增 11）；`stdio-service` 1 test 通过且 `uv run python src/main.py` 输出模板就绪；`git diff --check` 通过。
- 未改动 runtime 生产代码、ExecutionRecord、Worker Lease 或服务模板接口；只加测试文件与配套 import。

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。

**2026-10-23T07:07:05Z**

2026-10-23：以 Frank Qi 身份完成实现。新增 PyYAML 6.0.3（来源 PyPI，MIT，MCP 卡片 YAML 解析用途），通过 mcp-libs/pyproject.toml 与 uv.lock 声明；新增 custom-mcp/stdio-service 独立 uv 子项目、local-mcp-libs YAML 卡片、stdio/Streamable HTTP 连接字段和安全启动校验。验证：MCP registry 5 tests、runtime 14 tests、自定义服务 1 test 均通过；uv 启动模板通过；git diff --check 通过。

**2026-10-23T07:07:33Z**

2026-10-23 修订：当前交付的是可复制的 uv 服务模板和注册卡片协议，尚未引入未确认版本的 MCP SDK，因此模板仅验证入口启动，不宣称已完成真实 MCP 协议握手。真实 MCP Server 实现与 SDK 依赖应另行确定版本后补充。
