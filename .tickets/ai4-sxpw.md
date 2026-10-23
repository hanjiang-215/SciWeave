---
id: ai4-sxpw
status: closed
deps: [ai4-eikj]
links: []
created: 2026-10-23T05:18:24Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-o2n3
tags: [implementation, task-agent, workflow, runtime, fast-agent, config]
---
# 规范 Workflow YAML 协议并实现 runtime 转换器

将当前 runtime 内部工作流模型收敛为稳定的 Workflow YAML 协议，并实现从 YAML 文件/目录读取、校验、解析引用和转换为 runtime 执行配置以及 fast-agent 适配输入的功能。协议覆盖 Router、Orchestrator、Parallel、Agents as Tools 四种类型，明确入口 Agent、子 Agent、汇总 Agent、最终写入 Agent、版本和错误语义。保持 ExecutionRecord、Worker Lease、服务模板接口不变。

## Design

1. 在 agent-definitions/workflows/ 固化 YAML schema、版本字段和四类工作流示例。
2. runtime 提供路径读取、YAML 解析、schema/引用/循环校验、稳定配置对象和转换入口。
3. 转换层输出 runtime WorkflowDefinition，并为后续 FastAgentRuntimeAdapter 保留明确边界；不把 fast-agent 私有实现泄漏到配置模型。
4. 所有路径、外部地址和凭据继续通过环境变量提供；测试使用临时目录、假运行时和无固定端口。

## Acceptance Criteria

- [ ] Workflow YAML 协议文档和 schema 明确版本、类型、入口、子 Agent、summarizer、final_writer 及引用规则。
- [ ] runtime 可从单文件或配置目录读取 Workflow YAML，并产生稳定的已校验配置对象。
- [ ] Router、Orchestrator、Parallel、Agents as Tools 四类配置均有可运行的最小测试。
- [ ] 缺字段、未知 Agent、未知类型、循环引用和不兼容版本返回稳定错误。
- [ ] 提供从项目 YAML 到 runtime 执行模型/fast-agent 适配输入的转换入口。
- [ ] 不改变 ExecutionRecord、Worker Lease、Worker 启动接口和服务模板边界。
- [ ] 依赖通过 runtime 的 pyproject.toml 和 uv.lock 声明，并记录来源、用途、许可证/限制和验证命令。
- [ ] runtime 测试和 git diff --check 通过。


## Notes

**2026-10-23T07:07:05Z**

2026-10-23：以 Frank Qi 身份完成实现。新增 PyYAML 6.0.3（来源 PyPI，MIT，runtime YAML 解析用途），通过 runtime/pyproject.toml 与 uv.lock 声明；实现 load_workflow_yaml、目录合并、1.x 版本校验、稳定错误和 workflow_to_fast_agent_input。新增 Workflow YAML 协议文档与 schema。验证：runtime 14 tests passed，git diff --check 通过。
