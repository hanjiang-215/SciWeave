---
name: owner-dispatch-root-task
description: 启动一条路线——派发根任务，并判断「没派出去」到底缺什么。
---

# 派发根任务

```
dispatch_root_task(
  mapping_domain_id="...",
  task_node_id="...",
  target_node_version_ref="...",
  trigger_revision_id="...",
)
```

只有这一个工具，因为路线只从这里开始。

## 为什么必须由你点这一下

正式版本发布（`formal_revision_published`）**不会**自动派发根节点。这条决定的代价很直接：
一条刚发布的路线不会在有人保存它的瞬间开始花钱。后继节点则由上游交接自动触发——
那是安全的，因为上游已经跑完、结论已经在手。

所以：发布了路线却没有派发，是「一条安静的、什么都没发生的路线」，而不是一个报错。
没有告警能告诉你「本该有人点这一下」。

## 四个参数都必须准确

| 参数 | 从哪来 | 错会怎样 |
| --- | --- | --- |
| `mapping_domain_id` | 你要启动的那个域 | 拿不到最新正式版本，直接 `not_dispatched` |
| `task_node_id` | 正式图里的节点 id | 节点不在最新快照里 ⇒ `not_dispatched` |
| `target_node_version_ref` | 该节点在这次的版本引用 | 派发记录按它去重，写错会重复派发 |
| `trigger_revision_id` | 你依据的那个正式版本 | 派发记录与触发版本对不上，事后无法追 |

`task_node_id` 与 `target_node_version_ref` 是两个东西。节点 id 在多个正式版本里是同一个，
版本引用指向具体那一次。只填前者会在下一次正式版本后让这条派发记录看上去属于新版本。

## 节点必须是根

服务端会检查：**有入边就不是根，直接拒绝**（抛错，返回 `dispatch_failed`）。
这不是可以绕过的校验——一条有上游的节点应该在它的上游完成后自动开始，
手动派发会让它在上游还没出结论时就跑起来，而下游工作会建在一个不存在的结论上。

看到 `dispatch_failed` 而你又确信它是根，先确认你看的是**最新**正式快照：
某次正式化可能刚给这个节点加了一条入边。

## `accepted=false` 时到底缺什么

派发失败有两种，通知类型不同，修的也不是同一个人：

| 返回 | 实际含义 | 该做什么 |
| --- | --- | --- |
| `dispatch_not_accepted` | 根节点没派出去 | 看下面三条 |
| `dispatch_failed` | 调用本身出错（含非根节点） | 先确认节点与版本，再看 `not a root node` 之类的报错 |

`dispatch_not_accepted` 的三条来源，由 `_select_executor` 决定：

1. **`workflow_binding_required`** —— 节点的 `executor_refs` 是空的。这是映射本身的缺陷：
   节点没有指定任何执行者。修法是在正式路线里给这个节点补执行者（那需要新候选、预审、正式化），
   不是反复重点派发。
2. **`workflow_load_failed`** —— 声明的执行者**一个都没在注册表里**。通常是名字写错，
   或者研究员换了 agent id 却没改映射。这是要你去修映射的错。
3. **`agent_unavailable`** —— 执行者注册了，但没有一个可用。这是运维问题：研究员的机器关了、
   服务没起、或实例状态不是 `online`。这时不该改映射。

**「未知」不等于「不可用」。** 三种状态分开看：注册表说没有这个 agent 是一个事实；
连不上注册表是另一个事实，它不能推出「没有」。混着处理会让人去修一个没坏的东西。

## 判断执行者到底在不在

```
get_agent_registration(agent_id="...")
```

看两件事，缺一不可：

- `agent.status == "active"`；
- `instances` 里至少有一个 `runtime_status == "online"`。

只注册了 agent 而没有任何实例，是一个**谁都投递不到**的 agent——它看起来在册，实际不可达。
这正是 `register_workflow_agent` 之后必须再 `register_agent_instance` 的原因。

## 你不做的

- 派发非根节点。下游节点等上游交接，绕过去就是绕开依赖边。
- 用派发接口「重试」一个卡住的节点。它是幂等的，重复调用不会让它更快；
  卡住的原因在 `pending_handoff` 里，去看那个。
- 替研究员启动他的 Task Agent。执行者不可用是通知，不是你去远端重启。
