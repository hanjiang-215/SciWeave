---
id: ai4-xncm
status: closed
deps: []
links: []
created: 2026-10-27T15:39:09Z
type: bug
priority: 1
assignee: hanjiang
tags: [coordinator, kafka, reliability]
---
# coordinator 容忍 broker 短暂不可达：轮询异常不应终止进程

容器实跑时观察到 coordinator 在 Kafka 短暂不可达后直接退出（kafka-python 的 NoBrokersAvailable / KafkaError 从 events.poll() 冒泡到 serve_forever），supervisord 反复重启形成 FATAL 循环。既有的毒事件处理只包住了单条事件，没包住 poll 本身。部署评审期只要 broker 抖动一下，协调流程就整体停摆。

## Acceptance Criteria

1) 轮询周期内的异常（poll/commit/适配器）不再终止 serve_forever，而是记录日志后按退避重试；2) 退避有上限且恢复后回到正常轮询间隔；3) stop() 在关闭失败时不让异常掩盖退出；4) 新增测试：假 events 端口连续抛错时循环仍在并最终恢复正常轮询；5) coordinator 全量测试通过。


## Notes

**2026-10-27T15:56:55Z**

﻿**2026-10-27 交付（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`。

容器实跑时发现两个同源问题：

1. **coordinator 被 broker 抖动打死**：`events.poll()` 抛出的 `NoBrokersAvailable` / `KafkaError` 从 `poll_once` 冒泡出 `serve_forever`，进程退出，supervisord 重启进同一故障，形成 FATAL 循环。改为在循环内捕获、按指数退避重试（上限 `max_poll_backoff_seconds`，默认 30s），成功一轮后回到正常间隔；`stop()` 的异常也不再掩盖退出原因。
2. **KafkaProducer 构造期同步等元数据**（默认 60 秒），broker 不可达时抛 `KafkaTimeoutError`。发布器在进程启动路径上构造，于是「配了队列但队列暂时不通」会连带把管理 MCP 弄成 FATAL（wiki-mcp 在容器里稳定 60 秒后退出即此因）。两个领域的发布器都改为**首次发布时才连接**；领域写入路径的 `_publish_safely` 本来就兜住异常。

同时修好 `sci-weave/centre-stack/compose.local-redpanda.yaml`：原来只设了 `SCIWEAVE_CENTRE_KAFKA_BOOTSTRAP`，而 compose 插值在解析阶段就把它展开进各角色的变量，容器里没有任何东西再读这个键；改为逐个覆盖 mapping/wiki/coordinator/queue 的 bootstrap。

验证：coordinator **87 passed**（新增 `test_a_broker_outage_does_not_kill_the_loop`，假 events 连续抛错 3 次后正常退出，断言轮询次数 ≥ 4 且进程收尾干净）；research-map **134 passed / 5 skipped**（新增惰性连接回归）；容器实跑 **11/12 RUNNING 稳定超过 100 秒**（此前 wiki-mcp 与 mapping-mcp 会在 60 秒后转 FATAL），Redpanda 中 `coordinator` 消费组状态 **Stable**。

未验证：真实 broker 断开-恢复的长时间演练；只覆盖了单轮退避与恢复路径。
