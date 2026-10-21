---
id: ai4-upsm
status: open
deps: []
links: [ai4-he04, ai4-rlv6]
created: 2026-10-21T12:14:23Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, audit, buffer, mcp]
---
# 中央服务留痕工具：写入方统一调用的审计接口

中央服务器上所有改动正式事实的组件共用一套固定留痕接口。留痕不是中央 Agent 的私有能力，而是写入方在写事实的同一事务里必须调用的工具。

## Design

依据「中央协调 Agent 与审计体系」的字段清单（actor、actor_type、operation、target_id、base_revision、candidate_revision、result、timestamp、reason，以及关联的 Proposal/Task/Resource 标识）定出统一事件形状和一个只追加的写入接口。

调用方至少包括：Buffer 写预审结论、Research Mapping 管理 MCP 推进正式版本、LLM-Wiki 管理 MCP 推进正式版本、Task Agent Gateway 写 OwnerCommand 与 Execution Record。

约束：只追加，不提供更新和删除；调用方不能自定义省略字段；查询入口与写入分离，写入口不暴露给 Agent 自由调用。

## Acceptance Criteria

- 事件字段与「中央协调 Agent 与审计体系」一致，并有事件类型枚举
- 写入接口只能在事实写入事务内调用，独立调用被拒绝
- 无更新或删除接口
- 按任务、Proposal、正式版本、时间的查询可重建"谁在什么基准上做了什么、结果如何、谁批准"
- 至少一个写入方接入并有回归测试


## Notes

**2026-10-21T13:18:42Z**

2026-10-21T21:20:30Z

调用方清单变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)。本票 Design 中的调用方之一「Task Agent Gateway 写 OwnerCommand 与 Execution Record」需要澄清：

- OwnerCommand 与 Execution Record 现在落在研究员本机的 SQLite，不再进入中央。
- 端侧 agent 进入中央的事实只有草稿提交，其留痕由草稿箱（`centre-control/buffer`）作为写入方调用本工具完成。
- 因此留痕工具的调用方集合中，端侧不再直接出现，改为经由草稿箱。

仍成立的调用方：Buffer 写预审结论与草稿审核结论、Research Mapping 管理 MCP 推进正式版本、LLM-Wiki 管理 MCP 推进正式版本。

未定：草稿提交本身算不算「改动正式事实」，要不要留痕。按现有定义它不是正式事实，倾向于只在草稿状态变更（提交、审核、转候选）时留痕。
