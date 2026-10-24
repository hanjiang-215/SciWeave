---
id: ai4-jnkn
status: open
deps: []
links: [ai4-6ljq, ai4-orpg, ai4-emsk, ai4-gvan]
created: 2026-10-21T08:58:49Z
type: task
priority: 1
assignee: hanjiang
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


**2026-10-22T13:20:00Z**

补充实现位置：中央留痕工具共享包。

- 原路径 `sci-weave/shared/audit-trail`，迁到 `sci-weave/centre-control/shared/audit-trail`。迁移由 [留痕包迁移到 centre-control 并改造为接口层调用账本](ai4-gvan.md) 执行。
- `centre-control` 仍不是项目组、各目录仍不共用锁文件；`centre-control/shared/` 是**代码归属边界**，表示「部署在中央的多个独立项目共用这段代码」，不表示同一个部署单元，也不产生组级 `pyproject.toml` 或组级 `uv.lock`。
- 各调用方以 uv `[tool.uv.sources]` path 可编辑依赖引用该包，各自提交自己的锁文件。
- 迁移后 `sci-weave/shared/` 目录清空，规则上也不再保留这个顶层共享目录的名称。

## Notes

**2026-10-24T10:08:22Z**

转交说明（2026-10-24）：assignee 由 Frank Qi 改为 hanjiang，依据 Gitee issue https://gitee.com/qi-yueran/ai4science/issues/IKQ63M 的第 1 条请求与本节裁决。原负责人 Frank Qi，转交原因：正文描述的落位已在仓库落地（sci-weave/centre-control/research-map、research-wiki、shared/audit-trail 均存在），剩余为核对与验收回写，由实际承建方 hanjiang 确认更准确。
