---
id: ai4-fv1r
status: open
deps: []
links: [ai4-he04, ai4-5z9e, ai4-oebi, ai4-rlv6, ai4-upsm, ai4-te1v, ai4-dhpv, ai4-ujvn, ai4-xem8, ai4-z3z4]
created: 2026-10-21T15:36:18Z
type: epic
priority: 1
assignee: Frank Qi
tags: [wayfinder:map, centre-agents, governance]
---
# 中央 Agent 候选预审职能地图

中央 Agent 只做一件事：对 Research Mapping 与 LLM-Wiki 的候选做预审，并在需要时生成混合候选。本地图收敛它的产物、存储、触发、门禁与接口边界。

## Destination

形成可交给实现的中央 Agent 规格：它从两套互相隔离的领域管理 MCP 读取候选，产出纳入预审报告表的结论与冲突矩阵，必要时生成混合候选分支，并把结论交给 Project Owner 选择。它不写正式版本、不发起执行、不下发任务、不部署或托管端侧 Agent。

## Notes

领域：中央 Agent 的职责边界、预审产物与调用面。

讨论基线（2026-10-21 第五轮，已由用户逐条裁决）：

- 中央 Agent 只保留预审一类职能，其余能力一律不加。
- 预审报告以**只追加日志**的形式写入领域治理记录，不走草稿箱。
- 一次预审的范围是**所有可能转为正式版的候选**，不限于同一基准版本。
- 预审是**硬门禁**：中央服务不可用时阻塞并排查，不设「未经预审也可批准」的放行通道。
- 混合候选保留，作者记为**全部来源作者**，但来源作者对它没有任何操作权。
- 注册表增加中央 Agent 这一类，与端侧 Agent 用 `kind` 区分。
- 预审与混合的写权限**分开授权**：写预审日志与新建混合候选是两个独立工具。

相关但不属于本地图：触发消息的队列语义由「消息队列协作模型分支」(ai4-te1v) 定义；留痕接口由「中央服务留痕工具」(ai4-upsm) 定义；草稿箱契约由「中央草稿箱的存储与审核契约」(ai4-xem8) 定义。本地图只在消费它们时引用，不改写其内容。

## Decisions so far

<!-- 已关闭的子票在这里各占一行；未关闭的子票通过查询获得，不在此列出 -->

本图当前没有已关闭的子票。

## Not yet specified

两套管理 MCP 分别暴露候选读接口时的返回形状是否需要统一：Mapping 与 Wiki 的候选结构本就不要求一致，但预审报告要放在一起呈现给 PO，呈现层的一致性程度待定。

## Out of scope

- 任务下发、调度、重试、转交：已随「Agent 以消息驱动，Gateway 的 MCP 只负责返修」(ai4-dhpv) 改由消息队列与端侧自行处理。
- 部署、绑定或托管端侧 Task Agent：已随「Task Agent 改由研究员端侧自持」(ai4-we38) 取消。
- 推进正式版本：由 Project Owner 经自己的 MCP 完成。
- 独立的人员与 Agent 注册服务：退化为事实留痕表，见「注册表登记中央 Agent 与开放面第四档」(ai4-t2wc)。
- 写审计：由「中央服务留痕工具」(ai4-upsm) 的固定接口承担，中央 Agent 无私有审计通道。

**2026-10-22T09:35:00Z**

2026-10-22 更新（本票 assignee 本人操作）：

- **`Not yet specified` 中「预审与正式版本发布之间的时序」已定案，移出**：正式版本发布也发一条领域事件，受影响候选的旧报告标 `stale` 并在下一次预审时重算，重算完成前该候选卡住。落在「预审报告的追加日志契约」(ai4-oz3s) 与「预审门禁、触发范围与故障处置」(ai4-a2ba)。
- **Decisions so far 中「中央服务留痕工具」一行已移出**：该票当前仍是 `open`，按要求 Decisions so far 只收已关闭的子票，故不在此列出，待其关闭后再转载。
- **地图形态补充**：Centre Agent 与 Task Agent 共用 Work Agent 架构，见 `docs/data-flow/work-agent.md` 与 [ADR-0001](../../docs/adr/0001-task-dispatch-via-message-queue.md)。本图的产物、存储、门禁与接口边界不受影响，变的是它跑在三个组件上而非单个常驻进程。
