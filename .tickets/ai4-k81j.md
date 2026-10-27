---
id: ai4-k81j
status: closed
deps: []
links: []
created: 2026-10-27T15:39:09Z
type: chore
priority: 2
assignee: hanjiang
tags: [mcp, docs, capabilities]
---
# 领域 MCP 工具描述与能力实现不一致：centre 不解锁写工具

research-map / research-wiki 的写工具 description 与 README 写着 'Requires candidate_submit or centre capability' 之类，但 _TOOL_CAPABILITIES 的实际语义是 centre 只解锁 4 个读工具，写工具必须显式授予 candidate_submit / candidate_review / formalize / prereview_log / merged_candidate。按文档配置会得到 HTTP 200 + isError=true 的 forbidden，容易被误判为服务故障。

## Acceptance Criteria

1) 两个项目写工具的 description 去掉 'or centre'，读工具保留；2) 两个 README 的能力档说明与 _TOOL_CAPABILITIES 一致；3) 测试仍通过。


## Notes

**2026-10-27T15:56:55Z**

﻿**2026-10-27 交付（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`。

改动：research-map 与 research-wiki 的写工具 description 去掉 `or centre`（`candidate_submit` / `candidate_review` / `formalize` 各自只写自己的能力名）；两个 README 的候选提交说明改为「要求 candidate_submit 能力（centre 不解锁写工具）」，能力档段落补一句「centre 只解锁 4 个读工具（`get_formal_*`、`list_*`、`list_reviewable_*`）」。

验证：research-map **134 passed**、research-wiki **141 passed**，均无回归。

未改代码语义：`_TOOL_CAPABILITIES` 本来就是对的，这次只让文档与工具描述跟上实现。
