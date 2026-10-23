---
id: ai4-7zv3
status: closed
deps: []
links: []
created: 2026-10-22T17:18:54Z
type: task
priority: 1
assignee: hanjiang
parent: ai4-lrfz
tags: [dashboard, read-only, research-mapping]
---
# 提供 Research Mapping 看板只读快照来源

在现有 Research Mapping 正式查询边界内增加只读看板片段端点，投影当前正式 MappingRevision 的 TaskNode/DependencyEdge、路线摘要和正式版本观测事实，供 dashboard-api 通过 HTTP 读取。不复制或修改图数据，不把候选/未激活 Commit 显示为正式内容。

## Design

复用 FormalQueryService 和现有环境配置，使用 Python 标准库回环 HTTP seam；端点只返回 DashboardSnapshot 的 mapping fragment（projects/tasks/events/observedAt/sourceStatus），错误返回安全 reason_code。TaskNode 的执行状态只读取对象已有字段，缺失时显示 queued/状态未知，不凭空推断完成；所有地址/端口环境变量配置。

## Acceptance Criteria

只读端点能返回 available 正式快照的路线摘要、TaskNode、前置关系和正式发布事件；无正式指针、TerminusDB 不可用或跨存储不一致时返回可区分 sourceStatus；不访问候选内容；不提供 POST/PUT/PATCH/DELETE；使用临时 SQLite/Fake TerminusDB 和临时端口测试成功、无正式版本、不可用和安全错误；现有 Research Mapping 全量测试保持通过。


## Notes

**2026-10-22T18:20:55Z**

﻿2026-10-23??? Research Mapping ??????????? `src/research_mapping/dashboard_source.py` ? `tests/test_dashboard_source.py`?? `SCIWEAVE_MAPPING_DASHBOARD_MODE=1` ??? `GET /api/dashboard/source/mapping`??? `FormalQueryService`?????????? Commit ? TaskNode/DependencyEdge/??????????? Commit ????????????????? Bearer ???????? 405?

???`uv run --locked python -m unittest discover -s tests -v` ? 77 ????5 ??? TerminusDB ???????`uv run --locked python -m compileall -q src tests` ?????????????? Python ??????????????? `.env.example` ? README?
