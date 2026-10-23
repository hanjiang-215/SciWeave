---
id: ai4-s2nb
status: open
deps: [ai4-sxpw]
links: [ai4-cl3t]
created: 2026-10-23T07:12:26Z
type: feature
priority: 1
assignee: Frank Qi
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

- [ ] libs/agent-libs、libs/mcp-libs 不再包含 pyproject.toml、uv.lock、src 或独立测试项目。
- [ ] 新增 libs/workflow-libs，至少包含 Workflow YAML、schema/README 和四类工作流示例。
- [ ] runtime 提供 Agent、MCP、Workflow 三类资源的统一加载、版本、覆盖和稳定错误接口。
- [ ] 原有 agent-libs、mcp-libs 行为测试迁移到 runtime 并通过。
- [ ] runtime 可从环境变量或显式路径加载标准与本地资源，配置中不含真实凭据。
- [ ] custom-mcp 仍作为独立 uv Python 子项目，libs 只保存其注册卡片。
- [ ] runtime 依赖和唯一 uv.lock 更新，运行完整测试并通过 git diff --check。


## Notes

**2026-10-23T07:24:50Z**

2026-10-23：以 Frank Qi 身份完成第一阶段迁移。新增 runtime resources.py 和 mcp_resources.py，统一加载 Agent/MCP 配置资源；新增 libs/workflow-libs 及四类 Workflow YAML 示例；agent-libs、mcp-libs 已移除 pyproject.toml、uv.lock、src 和独立 tests，保留纯 YAML/JSON/README 资源；README 已更新。验证：runtime 16 tests passed、compileall 通过、git diff --check 通过。后续若需将所有旧注册表边界测试完整转移到 runtime，可继续补充。

**2026-10-23T07:28:39Z**

2026-10-23 修订：根据实现审查补充不存在资源目录和标准/本地重复 MCP 资源的稳定处理，避免静默覆盖；runtime 16 tests、compileall、git diff --check 仍通过。
