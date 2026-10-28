---
id: ai4-sjqd
status: open
deps: []
links: []
created: 2026-10-28T20:21:06Z
type: bug
priority: 2
assignee: hanjiang
---
# coordinator Kafka 消费组缺环境前缀，多栈并存事件被负载均衡

coordinator/src/main.py:77 默认消费组为 'coordinator'，docker sciweave-centre 容器与原生 dev-stack 同时运行时同组单分区消费，事件被随机分给任一方，原生协调器漏处理（B9）。测试时以临时改 coordinator-native 绕过，未根治。

## Design

消费组 id 应带环境前缀（如 coordinator-），启动日志显式打印实际消费组，避免跨部署负载均衡。

## Acceptance Criteria

两套栈并存时事件确定由预期一方消费；启动日志可见消费组名；不改动 topic 与分区语义。

