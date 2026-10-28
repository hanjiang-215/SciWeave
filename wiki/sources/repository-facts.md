---
type: source
created: 2026-10-28
updated: 2026-10-28
sources: []
tags: [source, repository, facts]
source_file: repository-working-tree
source_sha256: not-applicable
---

# Repository Facts

这是本 Wiki 的仓库事实汇总页。它不是替代源码和权威文档的单一规格，而是为 Wiki 页面提供可追踪入口。

## 主要来源

- 产品入口：[README.md](../../README.md)
- 产品总结：[humans/competition/project-summary.md](../../humans/competition/project-summary.md)
- 技术栈：[docs/TECH_STACK.md](../../docs/TECH_STACK.md)
- 依赖原则：[docs/DEPENDENCIES.md](../../docs/DEPENDENCIES.md)
- 验证命令：[docs/验证命令.md](../../docs/验证命令.md)
- 中央服务说明：[sci-weave/centre-control/README.md](../../sci-weave/centre-control/README.md)
- 单容器部署：[sci-weave/centre-stack/README.md](../../sci-weave/centre-stack/README.md)
- 部署决策：[docs/adr/0006-centre-single-container.md](../../docs/adr/0006-centre-single-container.md)
- Work Agent 数据流：[docs/data-flow/work-agent.md](../../docs/data-flow/work-agent.md)
- 消息与交接：[docs/data-flow/message-queue.md](../../docs/data-flow/message-queue.md)
- 草稿箱：[docs/data-flow/draft-buffer.md](../../docs/data-flow/draft-buffer.md)
- Centre Agent：[docs/data-flow/centre-agent.md](../../docs/data-flow/centre-agent.md)、[sci-weave/centre-control/centre-agents/README.md](../../sci-weave/centre-control/centre-agents/README.md)
- 套件说明：[sci-weave/toolkits/README.md](../../sci-weave/toolkits/README.md)

## 关键事实摘要

1. SciWeave 将版本化研究路线、Agent 执行、草稿、人审、候选预审和 Owner 正式化连接为闭环。
2. Research Mapping 与 LLM-Wiki 是独立领域，TerminusDB 保存图快照，SQLite 保存治理/运行状态。
3. `task_handoff_ready` 才能触发 Task Agent；通知事件不直接启动 Worker。
4. Worker 是短生命周期进程；执行完成后写入 Draft Buffer 并返回 `draft_id`。
5. 草稿 `accepted` 不自动创建候选；人通过领域 MCP 推进候选。
6. Centre Agent 预审和 Project Owner 正式化是不同职责。
7. Coordinator 不改 Map、不启 Worker；Registry 不授予执行权限。
8. 中央服务由 `centre-stack` 单镜像单容器部署，第三方 TerminusDB/Redpanda 独立运行。
9. 技术栈包括 Python/uv、Vue/Vite/Pinia、MCP Streamable HTTP、Bearer、Redpanda Kafka API、fast-agent-mcp。

## 验证摘要

`docs/验证命令.md` 记录最近一次全量结果：1204 个用例通过、12 个因缺少真实基础设施跳过；跨项目 CI 脚本另有 1319 passed / 22 skipped 的统计口径。项目总结还记录中心服务 compose 实跑和演示证据链。运行具体命令前以当前工作区和对应 README 为准。

## Contradictions

### Centre Agent ingest

`sci-weave/centre-control/centre-agents/README.md` 将首版能力写成范围声明，并提醒不代表全部实现；`gateway/ingest/README.md` 更明确写“仅骨架、未实现消费者、SQLite 表、租约或通知”。但 ingest 目录已有消费代码、测试，数据流和部署文档又描述了候选事件预审路径。因此 Wiki 只把 Centre Agent 的治理边界作为设计事实，把事件消费闭环标为“实现状态待核验”，不把单一 README 当成最终实现证明。

### 消息信封

`shared/message-envelope` 有协议包和测试，但 `docs/data-flow/message-queue.md` 明确说明当前零生产调用方，线上生产者仍使用各自扁平 dict。统一信封是目标格式，不应被描述成已经完成的生产契约。

### 部署文档历史

`docs/adr/0006-centre-single-container.md` 和 `centre-stack/README.md` 是当前单容器部署裁决；旧的多容器 demo-stack 只代表演示子集，不应与生产部署混用。
