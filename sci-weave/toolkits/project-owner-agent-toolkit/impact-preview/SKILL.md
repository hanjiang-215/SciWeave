---
name: owner-impact-preview
description: 批准之前读预审证据——改了什么、动了谁、路线会不会因此改变，以及哪些「没变」其实是没看到。
---

# 读影响范围

预审报告告诉你「过没过」，预览告诉你「改了什么」。两者不能互相替代：一份 `passed` 的报告
配上一个 `route_impact=changed` 的预览，仍然是「这条候选会改变路线」——那是你的决定，
不是预审能替你做的。

## 先拿准确的三个坐标

```
preview_candidate(
  proposal_id="...",
  base_formal_revision_id="...",   # 候选声明的基准
  candidate_head="...",            # 候选的精确 commit
)
```

两个都必填，而且必须来自候选本身（`list_candidates` 里就有）。`candidate_head` 写错的常见后果是
`candidate_mismatch`：服务端读到的分支头和你说的是同一个才继续。**不要**用「大约最新的那个
commit」——预览是按精确 head 比的，差一个 commit 比的就是别人的内容。

## 怎么读返回

| 字段 | 意思 | 容易误读的地方 |
| --- | --- | --- |
| `changes` | 逐字段的 before/after 摘要 | 摘要是 digest，不是正文。要看正文去领域读接口 |
| `affected_objects` | 被改动的对象 id 集合 | 空集合**不等于**「没改动」，见下 |
| `route_impact` | `changed` / `unchanged` | 只看 `TaskNode`/`DependencyEdge` 与含 route/activation/condition/input/output 的字段 |
| `preview_id` | 证据的稳定标识 | 它只对 `create_merge_request` 有用，别拿它去 `record_review` |
| `status` / `reason_code` | 预览本身成不成 | 不是候选的裁决，只是证据生成的结果 |

放大一条：`affected_objects` 为空通常意味着**没有逐字段差异**，可能是「内容相同」，
也可能是「两侧快照摘要一致而对象集合未展开」。不要用空集合去论证「这条候选什么都没改」——
要论证这个，去看 `changes`。

## `route_impact` 为什么单独存在

路线变更和内容变更的后果不同。改一句文档描述需要重跑受影响的任务；加一条 `DependencyEdge`
会改变**哪些节点还能被派发**，可能让一条已经跑完的路线重新变成「有条件未满足」。
同一条候选可以两者都做。

`route_impact=changed` 时，批准前至少确认：

1. 新增的依赖边会不会让某些节点永久等不到条件（看 `dependency_kind` 与激活条件）；
2. 有没有节点从「不可调度」变成「可调度」——那意味着会有新执行被触发；
3. 受影响的资源引用是否仍然指向存在的对象。

这三条预审也看，但它是**事实报告**；把「所以现在要不要放行」推给它，就是把裁决偷渡进预审。

## 预览通过 ≠ 可以批准

`preview_candidate` 返回 `status=passed` 只表示证据生成成功。它不检查：

- 预审报告是否仍是 `report_current`（`report_stale` 的候选不该批）；
- 批准者是不是这个域的 Project Owner（那是 `formalize_candidate` 才核对的）；
- 基准是否还是当前正式版本（`stale_base` 要到正式化才报）。

所以顺序是：**读预审状态 → 读预览 → 决定 → 记录决定 → 正式化**。
把「预览看起来没问题」当成「可以批」，中间那三层保护就白设了。

## 预览之后

`preview_id` 的下一站是 `create_merge_request(preview_id)`，它把预览锁成一个 buffer
并返回 `buffer_id`。**预览可以生成很多次，但 buffer 只有一个**（`buffer_id` 是
`preview_id` 的摘要），所以重复调用是幂等的。改了候选 head 之后重新预览会得到新的
`preview_id`，也就得到新的 buffer——旧的 buffer 不会自动作废，它只是再也对不上新 head 了。
