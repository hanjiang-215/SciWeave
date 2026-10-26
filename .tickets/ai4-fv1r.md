---
id: ai4-fv1r
status: closed
deps: []
links: [ai4-he04, ai4-5z9e, ai4-oebi, ai4-rlv6, ai4-upsm, ai4-te1v, ai4-dhpv, ai4-ujvn, ai4-xem8, ai4-z3z4]
created: 2026-10-21T15:36:18Z
type: epic
priority: 1
assignee: hanjiang
tags: [wayfinder:map, centre-agents, governance]
---
# 中央 Agent 候选预审职能地图

中央 Agent 只做一件事：对 Research Mapping 与 LLM-Wiki 的候选做预审，并在需要时生成混合候选。本地图收敛它的产物、存储、触发、门禁与接口边界。

## Destination

形成可交给实现的中央 Agent 规格：它从两套互相隔离的领域管理 MCP 读取候选，产出纳入预审报告表的结论与冲突矩阵，必要时生成混合候选分支，并把结论交给 Project Owner 选择。它不写正式版本、不发起执行、不下发任务、不部署或托管端侧 Agent。

## Notes

领域：中央 Agent 的职责边界、预审产物与调用面。

**2026-10-25 地图状态更新（hanjiang，地图 owner）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

- `ai4-rlv6`（中央 Agent 能力接口收口）2026-10-25 关闭，结论已转载进 `Decisions so far`（6 读 + 2 写工具面、三组能力名、鉴权与无私有审计通道、Gateway MCP 只返修）。
- `ai4-a2ba`（预审门禁）规格层已收敛（纳入范围、去抖、事件载荷、单候选门禁、不用租约），但实现类验收阻塞于 `ai4-te1v`（Frank Qi），已提 issue `IKQ8HY`。
- 地图仍 open：`ai4-a2ba` 实现验收未闭合（阻塞于 te1v）。其余预审链子票 `eex0/he04/5z9e/oebi/tg3v/8dgd/5auy` 均已关闭。

讨论基线（2026-10-21 第五轮，已由用户逐条裁决）：

- 中央 Agent 只保留预审一类职能，其余能力一律不加。
- 预审报告以**只追加日志**的形式写入领域治理记录，不走草稿箱。
- 一次预审的范围是**所有可能转为正式版的候选**，不限于同一基准版本。
- 预审是**硬门禁**：中央服务不可用时阻塞并排查，不设「未经预审也可批准」的放行通道。
- 混合候选保留，作者记为**全部来源作者**，但来源作者对它没有任何操作权。
- 注册表增加中央 Agent 这一类，与端侧 Agent 用 `kind` 区分。
- 预审与混合的写权限**分开授权**：写预审日志与新建混合候选是两个独立工具。

相关但不属于本地图：触发消息的队列语义由「消息队列协作模型分支」(ai4-te1v) 定义；留痕接口由「中央服务留痕工具」(ai4-upsm) 定义；草稿箱契约由「中央草稿箱的存储与审核契约」(ai4-xem8) 定义。本地图只在消费它们时引用，不改写其内容。

**2026-10-23 首版能力规格入口：** 中央 Agent 的能力范围、工具分组和通知边界记录在「中央 Agent 能力接口收口」(ai4-rlv6)；面向实现者的说明落在 `sci-weave/centre-control/centre-agents/README.md`。本轮只落盘规格，不实现新的 MCP、注册表或邮件投递代码。

## Decisions so far

<!-- 已关闭的子票在这里各占一行；未关闭的子票通过查询获得，不在此列出 -->

- [中央服务留痕工具：写入方统一调用的审计接口](ai4-upsm.md)：统一发生在**接口层**而非存储层。2026-10-22 修订后，留痕只记接口层对外调用（调用者、通道、服务、工具、目标、结果、耗时），不记业务语义；中央一个审计库、路径由环境变量提供；读操作单条 fail-open，写操作两阶段 fail-closed；包位置 `sci-weave/centre-control/shared/audit-trail`。规格见 [中央留痕工具共享包实现规格](ai4-tg3v.md)，代码落地见 [留痕包迁移到 centre-control 并改造为接口层调用账本](ai4-gvan.md)。领域审计表与调用账本作用域分开、互不写入。
- [预审报告的追加日志契约](ai4-oz3s.md)：两套领域 SQLite 各一张报告表与一张失效判定表，字段对齐但不共享；唯一键 `(candidate_id, candidate_head, rule_set_version)` 保证重审幂等；失效用**追加判定**（`head_moved` / `base_moved`）表达，报告行只读，当前有效报告由最新判定推出；冲突矩阵只在同领域内比较；规则版本无法解析时拒写。
- [注册表登记中央 Agent 与其开放面](ai4-t2wc.md)：注册表加 `kind` 区分 `endpoint` 与 `centre`，中央类目所属主体留空，不增加规则集版本等运行时字段，登记仍不参与鉴权。开放面按**能力名**计、平铺互不包含：6 个读工具（两领域各 3 个）用 `centre`；`append_prereview_log` 用 `prereview_log`；`create_merged_candidate` 用 `merged_candidate`，两者都以必需领域参数区分领域。两领域共 11 个写工具（提交候选、预审、正式化、对账、Wiki 审核决定）全部不授予中央 Agent。Project Owner 联系人字段移出本票，归 [端侧 Agent 的注册记录与中央服务开放面](ai4-ujvn.md)。摘除既有 `centre` 授权并补两个写工具由 [收紧管理 MCP 的中央 Agent 开放面并补两个预审写工具](ai4-5auy.md) 实现。
- [中央 Agent 能力接口收口](ai4-rlv6.md)：2026-10-25 关闭。接口形态定稿：6 读 + 2 写工具面，`centre`/`prereview_log`/`merged_candidate` 三组能力名分开；Bearer→actor 注入、服务端鉴权，中央 Agent 进注册表但只留痕不参与鉴权；无写审计私有通道；Gateway MCP 只返修不派发（任务由消息驱动）。面向实现者的说明落在 `sci-weave/centre-control/centre-agents/README.md`。剩余门禁语义由 [预审门禁、触发范围与故障处置](ai4-a2ba.md) 承载，其规格层已收敛、实现类验收阻塞于 `ai4-te1v`（issue `IKQ8HY`）。
- [预审门禁、触发范围与故障处置](ai4-a2ba.md)：2026-10-26 关闭。规格五层定稿：纳入范围三条机械判定且不按基准版本排除；事件由领域 MCP 自动发布（载荷只带目标标识）；正式版本发布也发事件，受影响候选的报告经追加 `base_moved` 判定转失效并触发重算，以新版本为基准的候选不受影响；去抖为同一候选短窗口一条事件 + 全量快照审；门禁粒度为单候选且不做整链冻结；故障时阻塞且可观测（候选列表带 `prereview_status`：missing_report / report_current / report_stale）；不用分发租约，重放靠 `(candidate_id, candidate_head, rule_set_version)` 唯一键幂等。实现落地：`research-map`/`research-wiki` 治理事件发布（857f823）与 `prereview_status` 投影（bc09372）；Centre Agent 侧消费方 `centre-agents/gateway/ingest`（订阅 `sciweave.governance-events`，consumer group `sciweave.centre-workflow.<workflow_id>`，formal_revision_published → base_moved + 重算触发，dedupe_key 幂等，三条回归测试覆盖连续 head 更新只触发一次 / 待审状态可见 / 正式版本发布只影响依赖版本，9 项测试 + 全组件回归绿）。

## Not yet specified

两套管理 MCP 分别暴露候选读接口时的返回形状是否需要统一：Mapping 与 Wiki 的候选结构本就不要求一致，但预审报告要放在一起呈现给 PO，呈现层的一致性程度待定。

## Out of scope

- 任务下发、调度、重试、转交：已随「Agent 以消息驱动，Gateway 的 MCP 只负责返修」(ai4-dhpv) 改由消息队列与端侧自行处理。
- 部署、绑定或托管端侧 Task Agent：已随「Task Agent 改由研究员端侧自持」(ai4-we38) 取消。
- 推进正式版本：由 Project Owner 经自己的 MCP 完成。
- 独立的人员与 Agent 注册服务：退化为事实留痕表，见「注册表登记中央 Agent 与其开放面」(ai4-t2wc)。
- 写审计：由「中央服务留痕工具」(ai4-upsm) 的固定接口承担，中央 Agent 无私有审计通道。

**2026-10-22T09:35:00Z**

2026-10-22 更新（本票 assignee 本人操作）：

- **`Not yet specified` 中「预审与正式版本发布之间的时序」已定案，移出**：正式版本发布也发一条领域事件，受影响候选的旧报告标 `stale` 并在下一次预审时重算，重算完成前该候选卡住。落在「预审报告的追加日志契约」(ai4-oz3s) 与「预审门禁、触发范围与故障处置」(ai4-a2ba)。
- **Decisions so far 中「中央服务留痕工具」一行**：该票后来已关闭，按地图规则转载回索引，见上方条目。
- **地图形态补充**：Centre Agent 与 Task Agent 共用 Work Agent 架构，见 `docs/data-flow/work-agent.md` 与 [ADR-0001](../../docs/adr/0001-task-dispatch-via-message-queue.md)。本图的产物、存储、门禁与接口边界不受影响，变的是它跑在三个组件上而非单个常驻进程。

**2026-10-22T14:55:00Z**

2026-10-22 更新（本票 assignee 本人操作）：

- **「预审报告的追加日志契约」(ai4-oz3s) 已关闭**，结论转载进 `Decisions so far`。这项原先只被视为存储形态的细节，实际定下了三件影响其他子票的事：失效是**追加判定**而非修改旧报告；两套领域库各一张表、不跨领域比较冲突；`rule_set_version` 的规则文件位置留给「中央 Agent 能力接口收口」(ai4-rlv6)。
- **`ai4-a2ba`、`ai4-8dgd`、`ai4-t2wc` 随之解除阻塞**，进入前沿。
- 上一轮 09:35 记录里「旧报告标 `stale`」的表述已作废，正确表述是追加 `base_moved` 判定；保留原文以便对照。

**2026-10-25 地图负责人转交（hanjiang 操作，经 Frank Qi 授权）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据 Gitee issue https://gitee.com/qi-yueran/ai4science/issues/IKQ8BD 第 1 条，Frank Qi 授权 hanjiang 直接转交本地图。转交原因：地图子票 eex0/he04/5z9e/oebi/tg3v/8dgd 已由 hanjiang 收口，a2ba/rlv6 同步转交后整张地图由 hanjiang 统一关闭。按地图规则，Decisions so far 由地图 assignee 维护，此后由 hanjiang 更新。正文与已定结论不改写，仅变更归属并记录。

**2026-10-27 地图收口与关闭（hanjiang，地图 owner）**

> *This was generated by AI during triage.*

身份核对：本票 assignee 为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。按「评审默认我自己」兜底，hanjiang 本人对本地图收口负责。

最后的前沿阻塞已闭合：`ai4-a2ba`（预审门禁、触发范围与故障处置）于 2026-10-26 关闭，其规格五层与实现（领域事件发布 857f823、`prereview_status` 投影 bc09372、Centre Agent 消费方 `gateway/ingest`）已转载进 `Decisions so far`。地图全部链接子票（he04/5z9e/oebi/rlv6/upsm/te1v/dhpv/ujvn/xem8/z3z4，及前沿 t2wc/oz3s/8dgd/5auy/a2ba/csyj）均已关闭。`Not yet specified` 唯一残留项（两套管理 MCP 候选读接口返回形状是否需要统一）为呈现层一致性程度待定，非阻塞项，留给后续实现期。

Destination 已达成：中央 Agent 规格（6 读 + 2 写工具面、预审追加日志契约、门禁语义、触发范围与故障处置）全部由已关闭子票承载，可交实现。地图关闭。
