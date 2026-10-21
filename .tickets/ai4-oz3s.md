---
id: ai4-oz3s
status: open
deps: []
links: [ai4-he04, ai4-5z9e]
created: 2026-10-21T15:36:40Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-fv1r
tags: [centre-agents, governance, prereview, wayfinder:grilling]
---
# 预审报告的追加日志契约

定义中央 Agent 预审结论的存储形态：以只追加日志写入领域治理记录，含候选头、基准版本、规则集版本、检查结论与冲突矩阵，唯一键保证重审幂等。

## Question

预审报告写在哪里、长什么样、被什么约束，以及它和候选状态如何对应。

## Design

### 存储位置与写权限

报告写入**领域治理记录**，与候选、Proposal 的治理记录同库。中央 Agent 对领域 MCP 的写入面只有两个工具，且分开授权：

| 工具 | 用途 | 约束 |
| --- | --- | --- |
| `append_prereview_log` | 追加一份预审报告 | 只追加，不可改、不可删 |
| `create_merged_candidate` | 新建混合候选分支 | 只能新建，不改动已有候选 |

写预审日志与写领域内容是两类不同的权限。合成一个工具等于让「能读候选」的凭据顺带获得「能改候选内容」的能力。

### 报告字段

| 字段 | 说明 |
| --- | --- |
| `report_id` | 稳定业务 ID |
| `candidate_id` | 被审候选 |
| `candidate_head` | 审计时的精确 Commit |
| `base_formal_revision_id` | 候选声明的基准正式版本 |
| `rule_set_version` | 判据版本号，指向仓库中受 Git 管理的规则文件 |
| `checks` | 逐项结论：检查名、判定、失败码、依据摘要 |
| `verdict` | 通过、不通过 |
| `conflict_matrix` | 与同批其他候选在同一逻辑对象上的冲突关系 |
| `created_at` | 生成时间 |

唯一键为 `(candidate_id, candidate_head, rule_set_version)`：同一候选同一 head 用同一版判据重审，返回首次报告，不产生第二份结论。这条同时替代了原先设想的分发租约——单实例常驻，重放靠幂等而非互斥。

### 追加与不可修改

日志是事实记录，不是工作区。同一候选出现新 head 时产生**新的**报告条目，旧条目保持原样并在新报告中标注它已被取代。不提供编辑或删除入口，包括对中央 Agent 自己。

### 判据版本化

`rule_set_version` 只记版本号和检查项清单，不记提示词全文。规则文件本身受 Git 管理，报告的结论要与当时的规则一致。这样事后能判断两次结论的差异来自候选变化还是判据变化。

### 与 Proposal 状态的关系

报告只提结论，不改 Proposal 状态。`stale`（基准过期）与 `conflict`（同对象冲突）是报告里的一列事实，由 Project Owner 在批准或驳回时处置。中央 Agent 不改写候选、不改 Proposal 状态、不建 Merge Request Buffer。

## Acceptance Criteria

- [ ] 报告字段完整，且不含判据全文，只含版本号与检查项清单
- [ ] 唯一键为 `(candidate_id, candidate_head, rule_set_version)`，重复审同一对象返回首次结论
- [ ] 日志只追加：无编辑、无删除入口，新 head 产生新条目
- [ ] 写报告与新建混合候选是两个独立工具，权限可分开配置
- [ ] 报告不修改 Proposal 状态、不写正式版本、不建 Merge Request Buffer
- [ ] 报告经留痕工具写入同事务审计，无独立审计通道
- [ ] 有回归测试覆盖重复审同一 head、候选头变化后新旧报告并存

## Notes

**2026-10-21T23:40:00Z**

来源：2026-10-21 第五轮讨论。用户裁决「有写权限，可以类似日志的方式保存」。

本票承接「中央 Agent 候选预审入口与结论回写」(ai4-he04) 中「结论写回领域治理记录」一项的形态定义。he04 负责入口与失效判定，本票负责存储形态。
