---
id: ai4-azx2
status: open
deps: [ai4-yl2o, ai4-56iu]
links: []
created: 2026-10-18T14:54:50Z
type: task
priority: 1
parent: ai4-xup8  # Research Mapping 与 Wiki 领域数据模型和持久化规格地图
tags: [wayfinder:grilling]
---
# TerminusDB 与 SQLite 正式化一致性及失败恢复规则

在 Mapping、Wiki 与 SQLite 治理模型确定后，收敛跨存储引用、正式化事务边界和失败恢复语义。

## Design

## Question
TerminusDB 持有完整候选/正式状态、SQLite 持有治理元数据时，如何保证二者关联一致且审计可追溯？请决定正式化的业务成功条件、提交顺序/确认边界、部分失败后的可见状态、重试或补偿规则，以及查询在两侧状态不一致时采用的权威版本。

## Notes
本票只讨论产品和领域一致性语义；不规定具体事务实现、API 或队列技术。依赖 Mapping、Wiki 和 SQLite 字段模型先完成。

## Acceptance Criteria

明确候选创建、PO 批准、TerminusDB 正式推进、SQLite 正式版本关联和通知的状态边界；明确每类失败/重试后的权威状态及审计要求；确认不存在未批准数据进入正式查询的路径。
