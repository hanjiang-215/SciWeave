---
name: researcher-register-instance
description: 把研究员的 Task Agent 与它的运行实例登记到注册表，让交接协调服务真的把任务投过来。
---

# 登记实例

交接协调服务在发布一条 `task_handoff_ready` 之前会查注册表：只有 **Agent 本身
`status=active`** 且 **至少一个实例 `runtime_status=online`** 才算 `AVAILABLE`。
「查不到」和「不可用」是两件事——查不到时协调服务报的是 `UNKNOWN`，不是「这个人不在」，
所以一个从没登记过的 Agent 会让交接停在 `pending`，而不是报错。这就是这个技能存在的理由。

顺序不能反：先登记 Agent，再登记实例。`register_agent_instance` 对一个没有
`workflow_agent` 行的 `agent_id` 直接返回 `agent_not_found`。

## 1. 登记 Agent

```
register_workflow_agent(
  agent_id="<SCIWEAVE_AGENT_ID>",
  workflow_id="<同一个 id 或你的工作流 id>",
  kind="endpoint",
  workflow_kind="task_agent",
  idempotency_key="register-agent-<agent_id>-v1",
  status="active",
)
```

`kind` 只能是 `endpoint` 或 `centre`。研究员登记 `centre` 会被拒（那是 Project Owner 的动作），
所以这里写 `endpoint`。`principal_id` 留空时服务端会绑定到令牌身份；研究员的令牌只能
给自己的 `principal_id` 登记实例，这是服务端的 `_require_self_or_owner`。

## 2. 登记实例

```
register_agent_instance(
  agent_id="<SCIWEAVE_AGENT_ID>",
  agent_instance_id="<主机名或部署名>",
  idempotency_key="register-instance-<agent_id>-<instance>-v1",
  runtime_status="starting",
)
```

`runtime_status` 只有四个值：`starting`、`online`、`offline`、`revoked`，其中只有 `online` 是可投递的。本地服务真的起来之后
再推一次 `online`；进程退出前推 `offline`。**不要**用一个恒定的 `online` 掩盖订阅器已经死了
——协调服务会继续往一个没人消费的 topic 投消息，交接停在 `pending` 而没人知道为什么。

## 3. 核对

```
health()
```

返回 `registry_unavailable` 说明存储或服务本身有问题，此时不要继续推 `online`。
更完整的核对（`get_agent_registration`）需要 `project_owner` 身份或 `service_role=centre`
的服务令牌，研究员令牌拿不到——这不是遗漏，是服务端的授权设计。需要看完整注册行时，
请 Project Owner 查。

## 什么时候重新登记

- 换了 `SCIWEAVE_AGENT_ID`：`agent_id` 变了，等于一个新的 Agent。
- 换了机器或部署目录：`agent_instance_id` 应该跟着变，否则两个实例共用一个身份，
  注册表里的实例状态会互相覆盖。
- 交接一直停在 `pending` 且 topic 里确实有消息：先查这里，再查订阅器。
