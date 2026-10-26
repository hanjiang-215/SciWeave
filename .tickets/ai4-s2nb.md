---
id: ai4-s2nb
status: closed
deps: [ai4-sxpw]
links: [ai4-cl3t]
created: 2026-10-23T07:12:26Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-o2n3
tags: [implementation, task-agent, runtime, config, agent-libs, mcp-libs, workflow-libs]
---
# 将 Agent、MCP、Workflow libs 收敛为纯配置资源

将 deploy-task-agent/libs/agent-libs、libs/mcp-libs 和新增 libs/workflow-libs 从独立 Python 项目迁移为 YAML/JSON/Markdown 资源目录。所有资源注册表、版本解析、覆盖规则、MCP 卡片校验和 Workflow 配置读取统一迁入 runtime；libs 不再保存 pyproject.toml、uv.lock、src 或 tests。保留 custom-mcp 下真正的 Python MCP 服务项目。

## Design

1. 新增 libs/workflow-libs/，保存 Workflow YAML 和协议说明。
2. 将 agent-libs、mcp-libs 的标准资源迁移到纯配置目录；local-* 继续作为配置资源。
3. 将 AgentResource/ResourceRegistry、MCPResource/MCPRegistry 及相关加载校验迁入 runtime，runtime 统一从资源路径读取。
4. 把原有资源注册测试迁移为 runtime 公共接口测试。
5. 删除 agent-libs、mcp-libs 的 Python 项目文件和独立锁文件；不改变 custom-mcp 独立 Python 项目边界。

## Acceptance Criteria

- [x] libs/agent-libs、libs/mcp-libs 不再包含 pyproject.toml、uv.lock、src 或独立测试项目。
- [x] 新增 libs/workflow-libs，至少包含 Workflow YAML、schema/README 和四类工作流示例。
- [x] runtime 提供 Agent、MCP、Workflow 三类资源的统一加载、版本、覆盖和稳定错误接口。
- [x] 原有 agent-libs、mcp-libs 行为测试迁移到 runtime 并通过。
- [x] runtime 可从环境变量或显式路径加载标准与本地资源，配置中不含真实凭据。
- [x] custom-mcp 仍作为独立 uv Python 子项目，libs 只保存其注册卡片。
- [x] runtime 依赖和唯一 uv.lock 更新，运行完整测试并通过 git diff --check。


## Notes

**2026-10-25 验收并关闭（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

2026-10-25 在 `feature/hanjiang` 复跑七项验收并全部勾选。验证证据：`libs/` 全树无 `pyproject.toml`/`uv.lock`/`*.py`/`tests`（扫描为空）；`workflow-libs` 含 router/orchestrator/parallel/agents-as-tools 四个示例与 README；runtime 提供 `load_agent_registry`/`load_mcp_registry`/`load_workflow_yaml` 三类加载入口与稳定错误码；`custom-mcp/stdio-service/pyproject.toml` 仍为独立 uv 子项目；runtime 提交 `uv.lock`；`uv run --locked python -m unittest discover -s tests` 通过（Ran 29）、`compileall` 通过、`git diff --check` 退出码 0。验收证据为当前 HEAD 实测，覆盖此前 Notes「后续可补充完整转移测试」的弹性项。

**2026-10-23T07:24:50Z**

2026-10-23：以 Frank Qi 身份完成第一阶段迁移。新增 runtime resources.py 和 mcp_resources.py，统一加载 Agent/MCP 配置资源；新增 libs/workflow-libs 及四类 Workflow YAML 示例；agent-libs、mcp-libs 已移除 pyproject.toml、uv.lock、src 和独立 tests，保留纯 YAML/JSON/README 资源；README 已更新。验证：runtime 16 tests passed、compileall 通过、git diff --check 通过。后续若需将所有旧注册表边界测试完整转移到 runtime，可继续补充。

**2026-10-23T07:28:39Z**

2026-10-23 修订：根据实现审查补充不存在资源目录和标准/本地重复 MCP 资源的稳定处理，避免静默覆盖；runtime 16 tests、compileall、git diff --check 仍通过。

**2026-10-25 转交（hanjiang）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。转交原因：Frank Qi 暂时无法继续推进项目，经其本人授权，由 hanjiang 接手本票后续推进与收口。原负责人 Frank Qi，转交时间 2026-10-25T12:41:00Z。转交只变更归属与记录，不改写正文与验收标准。
