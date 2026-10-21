---
id: ai4-jnkn
status: open
deps: []
links: [ai4-6ljq, ai4-orpg, ai4-emsk]
created: 2026-10-21T08:58:49Z
type: task
priority: 1
assignee: Frank Qi
tags: [architecture]
---
# 中央侧项目与服务的实现位置

记录 Research Mapping、LLM-Wiki、TerminusDB 和 Redpanda 之后的实现与部署位置。centre-control 只表示部署在中央服务器，其中每个目录仍是独立项目或第三方服务。

## Design

之后的位置：

- Research Mapping：`sci-weave/centre-control/research-map`。原 `sci-weave/research-mapping` 已移入此处，仍保持独立的 `pyproject.toml` 与 `uv.lock`。
- LLM-Wiki：`sci-weave/centre-control/research-wiki`。原 `sci-weave/llm-wiki` 已移入此处，仍保持独立项目。
- TerminusDB：`sci-weave/service/terminusdb`。不再使用 `dockers/service/terminusdb`。
- Redpanda：`sci-weave/service/redpanda`。不再使用 `dockers/service/redpanda`。消息队列不另写业务项目，由使用它的项目连接该服务。

后续 Mapping 与 Wiki 实现继续写在上述两个目录中，不要新建回 `sci-weave/research-mapping` 或 `sci-weave/llm-wiki`。已关闭工单中的旧路径是当时记录，不改写。

## Acceptance Criteria

Research Mapping、LLM-Wiki、TerminusDB、Redpanda 的后续实现位置已写明，并与 research-map、research-wiki 两张实现地图关联。

