# 消息信封纯协议包实现规格

- 日期：2026-10-26
- 关联工单：[`ai4-3zxu`](../../../.tickets/ai4-3zxu.md)
- 上游决策：[`ai4-te1v`](../../../.tickets/ai4-te1v.md)（已关闭）
- 状态：施工前规格已收敛

## 目的与边界

`sci-weave/centre-control/shared/message-envelope/` 在本规格撰写时还不存在。`ai4-te1v` 把统一信封定在这个路径，`HandoffPublisherPort` 的实现等它，当时没有任何一张票承建。

> 落地说明（2026-10-27）：该包已经落地在 `sci-weave/centre-control/shared/message-envelope/`，承接票 `ai4-3zxu`、`ai4-sv1u` 均已关闭。下文保留为设计记录。

本规格把 `ai4-te1v` 已定的协议落成一个可实现的库：**只做** schema 定义、序列化、反序列化、信封构造与校验。

不做的事：不持有 Kafka 客户端、不建连接、不起消费者、不含重试循环、不管理 topic、不做注册中心交互。各角色自行接入 `confluent-kafka`。

## 为什么这是一个纯协议包

三类消息只有两个生产者，消费方全是自家 Python 服务。这个规模下，把编解码和业务传输耦合在一起，会让每个使用方各自实现一遍校验，而校验一旦分叉，"容忍式读取"的规则就失效了。

纯协议包的收益是可测：给定一个字节串，能不能解、解出来字段对不对，与网络、与 broker 状态、与重试次数全无关。

## 协议内容

### 信封

| 字段 | 必填 | 语义 |
| --- | --- | --- |
| `message_id` | 是 | 一次发布的唯一标识 |
| `message_type` | 是 | 消息类型，见下表 |
| `schema_version` | 是 | 整数，首版为 `1`；精确匹配，无次版本号 |
| `dedupe_key` | 是 | 业务幂等键，重试发布时保持不变 |
| `occurred_at` | 是 | 事件发生时间 |
| `published_at` | 是 | 发布实际发生时间 |
| `producer` | 是 | 生产服务标识与可选实例标识 |
| `routing` | 是 | 分区键与可选 `target_agent_id` |
| `payload` | 是 | 业务载荷，结构由 `message_type` 决定 |

`occurred_at` 与 `published_at` 分离的意义：追加发布（例如补偿重算）时 `occurred_at` 保持原事件的时点，`published_at` 记录这次实际发出。合并成一个字段会让乱序无法判断。

### 消息类型与载荷

| topic | `message_type` | 载荷必填字段 |
| --- | --- | --- |
| `sciweave.task-handoff.<agent_id>` | `task_handoff_ready` | `mapping_domain_id`、`task_node_id`、`target_node_version_ref`、`target_agent_id`、`pending_handoff_id`、`trigger_revision_id`、`upstream_source_refs`、`dependency_edge_version_refs`、`executor_ref_snapshot` |
| `sciweave.governance-events` | `candidate_created` | `mapping_domain_id`、`candidate_id` |
| `sciweave.governance-events` | `candidate_head_updated` | `mapping_domain_id`、`candidate_id` |
| `sciweave.governance-events` | `formal_revision_published` | `mapping_domain_id`、`formal_revision_id` |
| `sciweave.governance-events` | `task_completed` | `mapping_domain_id`、`task_node_id`、`completed_version_ref`、`execution_id`、`draft_id`、`completed_at`、`result_ref` |

`sciweave.dependency-notice` 是保留 topic：目前没有任何生产者或消费者，`formal_revision_published` 与 `task_completed` 都由交接协调服务从 `sciweave.governance-events` 订阅。

`dependency_edge_version_refs` 与 `upstream_source_refs` 一起回答「这条交接依据的是哪几个正式版本」。只有一个入边时仍用数组，不退化为单值——形状随边数变化会让消费方写出两套分支。

`executor_ref_snapshot` 仅用于审计，不替代当前正式 Map 校验。它记录派发当时看到的执行者集合，事后能分辨「当时没有别的执行者」和「当时有但选错了」。

### 版本兼容

`schema_version` 是整数精确匹配。判定只有一条：不等即不支持。

兼容策略是**容忍式读取**：

- 同版本一律可消费；
- 消费方**必须忽略** payload 中的未知字段；
- 新增字段必须可选，并在协议包中声明文档化默认值；
- 已有字段名**不得改变用途**；
- 只有删除字段、改变字段语义或改变必填性，才升版本。

后两条是这套策略自己的约束，读不出来，只能守。尤其「字段名不得改用途」：容忍式读取看不出同名不同义，而这类改动比新增字段危险得多。

## 投影与校验的取舍

校验分三级，必须能区分：

| 情况 | 结果 |
| --- | --- |
| 解不成 JSON，或信封必填字段缺失/类型错 | 格式非法 |
| `schema_version` 不等于当前支持值 | 版本不支持 |
| `message_type` 未知 | 类型未知 |
| 载荷缺必填字段 | 载荷非法 |

四者不能合并成一个「反序列化失败」。消费方对它们的处置不同：格式非法是永久错误，版本不支持可能需要升级，类型未知可能是新版本发布方先上线，载荷非法是生产方 bug。

## 不做什么

- 不定义 topic 名、分区键、消费者组。这些 `ai4-te1v` 已定死，照抄即可。
- 不实现 Redpanda producer/consumer。
- 不建 Schema Registry 交互。首版不使用 Registry，这是 `ai4-te1v` 第五轮的裁决。
- 不承载 `human_notification_intent` 与 `task_terminal_summary`。这两类走 email-service 的 MCP，不进 Redpanda。
