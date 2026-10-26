---
id: ai4-a2ba
status: open
deps: [ai4-oz3s]
links: [ai4-te1v, ai4-dhpv, ai4-he04, ai4-5z9e]
created: 2026-10-21T15:37:05Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-fv1r
tags: [centre-agents, governance, prereview, wayfinder:grilling]
---
# 预审门禁、触发范围与故障处置

定义一次预审纳入哪些候选、消息触发与去抖、预审作为硬门禁的粒度，以及中央服务不可用时的处置。

## Question

什么时候跑预审、一次跑在哪些候选上、缺报告时能不能批准、中央服务挂了怎么办。

## Design

### 纳入范围

「所有可能转为正式版的候选」。判定为同时满足三条：

- 未被放弃；
- 未正式化；
- 未被 Project Owner 驳回。

**不区分基准版本。** 基准过旧的候选同样纳入，只在报告里标 `stale`。理由是 PO 需要在一处看到全貌，过期只是一列事实，不构成排除理由。

不纳入：已放弃、已正式化、已驳回、以及他人的半成品分支（没有以候选身份登记的分支）。

### 触发

消息由**领域管理 MCP 在候选创建与候选头更新时自动发布**，不由人手工发送。人工发消息一定会漏，而漏掉的那条没有任何告警能发现：候选存在、没人通知、一直躺着。

**正式版本发布同样发一条事件。** PO 推进正式版本后，所有以旧版本为基准的候选都可能需要重算；靠 PO 手动通知会漏，靠定时轮询会把「刚推进又刚批准」这段时间变成盲区。正式版本事件与候选事件走同一条订阅路径，Centre Agent 收到后把受影响候选的报告标 `stale` 并在下一次预审时重算。

去抖：同一 `candidate_id` 在短窗口内多次 head 更新只投一条事件；Centre Agent 收到信号后**拉取当前全量候选做一次快照审**，而不是逐条审。冲突判定要求同一时点的一致性快照，逐条处理会把两个前后脚提交的候选误判为不冲突。

事件载荷只带 `candidate_id` 与 `candidate_head` 用于去重，不带候选正文；正文由 Centre Agent 经领域 MCP 读。正式版本事件只带 `formal_revision_id` 与领域标识。

### 报告失效

预审报告只在两个时点仍然成立时有效：产生它的 `candidate_head` 与 `base_formal_revision_id`。任一移动即失效。

| 触发 | 处置 |
| --- | --- |
| 候选头变化 | 新 head 产生新报告条目，旧条目保留并标 `superseded_by` |
| 正式版本发布 | 受影响候选的旧报告标 `stale`，下一次预审时重算；重算完成前该候选卡住 |

**失效不等于放行，也不等于冻结全体。** 标了 `stale` 的候选在重算完成前处于卡住状态——硬门禁不变，粒度仍是单候选。没有以该旧版本为基准的候选照常可批。

失效判定不需要 PO 介入，也不需要定时轮询：正式版本发布本身就是一条事件，与候选事件走同一条订阅路径。

### 门禁粒度

预审是**硬门禁**，不存在「未经预审也可批准」的放行通道。粒度是**单个候选**：

- 已有报告的候选，PO 可以批准；
- 缺报告的候选卡住，等待预审完成。

不做整链冻结。整链冻结会把中心 Agent 的可用性放大成整个项目的单点，而已有报告的候选并不需要它在线才能被批准。

### 故障处置

中央服务不可用时**阻塞并排查**，不放行、不降级。这与「单候选粒度」并不矛盾：粒度说的是哪些候选能继续走，故障处置说的是它挂掉的那部分工作等它修好，而不是绕过它。

配套要求：中央 Agent 停止运行时，缺报告的候选必须能被 PO **看见卡在哪一步**，而不是表现为「点了批准没反应」。具体表现为预审队列可查、待审候选有明确状态。

### 不用租约

单实例常驻，恢复靠「预审报告的追加日志契约」(ai4-oz3s) 的唯一键幂等，不用分发租约。offset 在报告写完后再提交，重启重放不会产生第二份结论。

## Acceptance Criteria

- [x] 纳入范围可被机械判定，且明确不按基准版本排除
- [x] 事件由领域 MCP 自动发布，不依赖人工发送
- [ ] 正式版本发布也发事件；受影响候选的报告转 `stale` 并触发重算
- [x] 有去抖规则，且预审输入是同一时点的全量快照
- [x] 事件载荷只带目标标识，不携带候选正文
- [x] 门禁粒度为单候选，明确不做整链冻结
- [x] 故障时阻塞且可观测：PO 能看出候选卡在缺报告，而不是无响应
- [x] 明确不用分发租约，重放靠报告唯一键幂等
- [ ] 有回归测试覆盖连续 head 更新只触发一次、故障期间待审候选状态可见、正式版本发布只影响依赖该版本的候选

## Notes

**2026-10-25 规格层收口（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

规格五层全部定稿并勾选：纳入范围（三条机械判定、不按基准排除）、去抖（同 candidate_id 短窗口一条 + 全量快照审）、事件载荷只带目标标识、门禁粒度为单候选、不用分发租约（重放靠 `(candidate_id, candidate_head, rule_set_version)` 唯一键幂等，已在 `ai4-oz3s` 落库并有 `test_prereview.py` 覆盖 head_moved/base_moved 追加判定）。

剩余 4 项未勾选为**实现类**，全部依赖消息队列语义 `ai4-te1v`（Frank Qi，open）：

- 候选创建/候选头更新时由领域 MCP 自动发布事件；
- 正式版本发布事件 + 受影响候选报告转失效并触发重算；
- 中央服务不可用时的预审队列可查/待审候选状态可见；
- 覆盖这三种场景的回归测试。

按约定，本票实现部分的触发源、去抖载体和可观测队列都落在 `ai4-te1v` 收敛后的消息/预审触发实现里，因此暂不关闭；已通过 issue 知会 Frank Qi（见下）。

**2026-10-26 实现两块落地（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

`ai4-te1v` 已于 2026-10-25 收敛关闭，上述阻塞解除，本轮把可闭环的两块实现落地并勾选：

**事件自动发布**（验收第 2 条）——提交 `857f823`：`research-map` 新增 `governance_events.py`（GovernanceEvent 信封、`candidate_event`/`formal_revision_event`、`KafkaGovernanceEventPublisher`/`Recording`/`Noop`），`MappingManagementService` 注入 `GovernanceEventPublisher` 端口，`submit_candidate` 成功发布 `candidate_created`（target=submission_id，与候选身份一致）、`formalize_candidate` 成功发布 `formal_revision_published`；`_publish_safely` 保证队列故障不回滚已持久化的治理事实，由 Centre Agent 全量快照扫描兜底恢复。载荷只带 `candidate_id`+`candidate_head`/`formal_revision_id`，符合"不携带候选正文"。新增 `test_governance_events.py`（6 项）与 `test_management.py` 的 `test_candidate_submit_publishes_governance_event`。

**故障时可观测**（验收第 7 条）——提交 `bc09372`：`research-map` 与 `research-wiki` 的 `list_*_reviewable_candidates` 工具为每个候选附加 `prereview_status` 投影（通过新增 `SqliteStore.prereview_status` + `MappingPrereviewLog.status_for_candidate`）：`missing_report`（缺报告、卡住）/ `report_current`（有当前结论，带 report_id/verdict/rule_set_version）/ `report_stale`（被 `head_moved`/`base_moved` 判定失效并带 reason）。PO 无需预审队列，直接从候选列表看出哪些候选卡在缺报告。未配置 prereview log 时省略该字段，向后兼容。各领域新增 `test_reviewable_list_exposes_prereview_status`（覆盖三种状态）。

**仍未勾选**：正式版本发布事件已发，但"受影响候选报告转 stale 并触发重算"的订阅处理在 Centre Agent 侧消费方实现（`ai4-csyj`/`ai4-fv1r` 下游）；回归测试第 9 条中"正式版本发布只影响依赖该版本的候选"需 Centre Agent 订阅路径落地后一并补测。本票保持 `open`。

**2026-10-25 负责人转交（hanjiang 操作，经 Frank Qi 授权）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据 Gitee issue https://gitee.com/qi-yueran/ai4science/issues/IKQ8BD 第 1 条，Frank Qi 授权 hanjiang 直接转交。转交原因：预审链其余子票（ai4-eex0/he04/5z9e/oebi）已由 hanjiang 收口，本票是预审链最后一张门禁票，转由 hanjiang 统一推进与关闭。正文与验收标准不改写，仅变更归属并记录。

**2026-10-21T23:40:00Z**

来源：2026-10-21 第五轮讨论。用户裁决：一次审「看所有可能可以转为正式版的候选」；中央服务出问题「不用这么麻烦，中央服务如果有问题应该阻塞排查」。

队列侧的语义（主题、分区、offset 提交）由「消息队列协作模型分支」(ai4-te1v) 定义，本票只消费。

**2026-10-22T09:22:00Z**

2026-10-22 补充「报告失效」一节，依据 Project Owner 裁决「stale 后重算，重算期间该候选卡住」：正式版本发布也发一条领域事件（载荷只带 `formal_revision_id` 与领域标识），受影响候选的旧报告转 `stale` 并在下一次预审时重算，重算完成前卡住；未以该版本为基准的候选不受影响。新增一条验收与对应回归测试要求。原文中「中央 Agent」已按术语统一改称 Centre Agent。

**2026-10-22T14:55:00Z**

「预审报告的追加日志契约」(ai4-oz3s) 关闭后的口径同步（本票 assignee 本人操作）。以下三处按该票的最终契约读，正文原文保留不动：

- 「报告里标 `stale`」：改为**追加一条 `reason='base_moved'` 的失效判定**，报告行本身不被修改。`stale` 不再是报告的字段值。
- 「旧条目保留并标 `superseded_by`」：改为追加 `reason='head_moved'` 的判定，`superseding_report_id` 指向新 head 的报告。`superseded_by` 字段已从报告表删除。
- 「下一次预审时重算」：重算产生的是新 head 下的新报告，与判定条目并存；「当前有效报告」由同一候选最新的一条判定推出。
