---
id: ai4-u5e6
status: closed
deps: []
links: []
created: 2026-10-27T15:39:09Z
type: feature
priority: 1
assignee: hanjiang
tags: [wiki, governance, events]
---
# research-wiki 治理事件接线：候选提交与正式发布要发事件

research-wiki 的 WikiManagementService 早已接受 governance_events 端口并有 _publish_safely，但 src/main.py 构造时没有传入，WikiConfig 也没有 Kafka 配置项。结果是 wiki 的候选提交与正式发布不产生任何事件，Centre Agent 与交接协调只能靠快照扫描发现 wiki 变化。research-map 侧存在同族缺陷（配置项读取后丢弃），已在 ai4-e1jk 修复，本票按同一形状补齐 wiki。

## Acceptance Criteria

1) WikiConfig 新增 governance_kafka_bootstrap 字段并由 SCIWEAVE_WIKI_KAFKA_BOOTSTRAP 填充，测试覆盖有值/无值两种情形；2) llm_wiki.governance_events 提供 create_governance_publisher(bootstrap, producer_factory=...)，有 broker 时返回 KafkaGovernanceEventPublisher、无 broker 时返回 Noop；3) src/main.py 把 publisher 注入 WikiManagementService；4) 新增回归测试证明配置能到达 publisher 选择；5) .env.example 与 centre-stack compose 补上该变量；6) research-wiki 全量测试通过。


## Notes

**2026-10-27T15:56:55Z**

﻿**2026-10-27 交付（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`。

改动：`WikiConfig` 新增 `governance_kafka_bootstrap`（来源 `SCIWEAVE_WIKI_KAFKA_BOOTSTRAP`，显式传给 dataclass——research-map 同族缺陷正是「读进局部变量没传」）；`llm_wiki.governance_events` 新增 `create_governance_publisher(bootstrap, producer_factory=...)`，并让 `KafkaGovernanceEventPublisher` 支持注入 producer；`src/main.py` 把 publisher 注入 `WikiManagementService`；`.env.example` 与 `sci-weave/centre-stack/compose.yaml` 补上该变量。

验证：research-wiki **141 passed / 12 skipped**（原 136，新增 `tests/test_config.py` 5 项：配置字段、未设情形、publisher 选择、惰性连接）。

未验证：wiki 候选提交 → 事件 → 下游消费的真实端到端没有演练（只到单元级）。另：coordinator 的消费者只读 `mapping_domain_id`，wiki 事件不会触发交接派发，这是设计边界，不是漏做。
