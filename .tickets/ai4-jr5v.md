---
id: ai4-jr5v
status: open
deps: []
links: []
created: 2026-10-26T18:38:15Z
type: bug
priority: 2
assignee: hanjiang
tags: [gap, centre-control, research-wiki]
---
# Wiki 资源审批缺少精确版本定位来源，带引用的候选无法批准

ResourceReviewService 在 src/main.py 中没有注入 location_source 与 authorizer，_location_source 为 None 时恒返回 READ_UNAVAILABLE/exact_version_location_unknown，record_decision 的 approved 永远被拒；仓库内没有任何 ExactVersionLocationSource 实现。带 ResourceReference 的候选因此无法审核通过也无法正式化。

## Acceptance Criteria

实现基于治理记录的精确版本定位来源并注入 main.py。|或明确记录该能力未交付，并在文档与工具描述中标注带引用的候选暂不可批准。

