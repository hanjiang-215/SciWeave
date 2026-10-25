---
id: ai4-cl3t
status: open
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

- [ ] deploy-task-agent/custom-mcp/ 下存在遵守目录规范的可运行自定义 MCP 服务样例/模板。
- [ ] 自定义服务具有独立 pyproject.toml、uv.lock、src/main.py 和 tests。
- [ ] local-mcp-libs 提供可校验的服务注册卡片和工具注册示例。
- [ ] 注册卡片可表达 uv 启动或环境变量 URL 连接方式，但不保存真实令牌、不内嵌 Python 代码。
- [ ] runtime 能解析注册卡片并生成 MCP 连接配置，拒绝未知服务、未知工具和不符合权限边界的配置。
- [ ] 自定义服务可通过 uv 命令完成最小启动或协议握手验证。
- [ ] 依赖通过自定义服务 pyproject.toml/uv.lock 声明，记录来源、用途、许可证/限制和验证命令。
- [ ] 不修改现有 ExecutionRecord、Worker Lease 和服务模板接口；相关测试及 git diff --check 通过。


## Notes

**2026-10-25T07:03:11Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T07:03:11Z。

**2026-10-23T07:07:05Z**

2026-10-23：以 Frank Qi 身份完成实现。新增 PyYAML 6.0.3（来源 PyPI，MIT，MCP 卡片 YAML 解析用途），通过 mcp-libs/pyproject.toml 与 uv.lock 声明；新增 custom-mcp/stdio-service 独立 uv 子项目、local-mcp-libs YAML 卡片、stdio/Streamable HTTP 连接字段和安全启动校验。验证：MCP registry 5 tests、runtime 14 tests、自定义服务 1 test 均通过；uv 启动模板通过；git diff --check 通过。

**2026-10-23T07:07:33Z**

2026-10-23 修订：当前交付的是可复制的 uv 服务模板和注册卡片协议，尚未引入未确认版本的 MCP SDK，因此模板仅验证入口启动，不宣称已完成真实 MCP 协议握手。真实 MCP Server 实现与 SDK 依赖应另行确定版本后补充。
