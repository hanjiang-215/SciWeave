---
id: ai4-dybh
status: closed
deps: []
links: [ai4-tg3v, ai4-ze1x, ai4-rh97, ai4-upsm, ai4-gvan]
created: 2026-10-22T02:31:06Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-tg3v
tags: [audit, shared, mapping, wiki]
---
# 领域审计表接入统一留痕接口

## Problem Statement

「中央留痕工具共享包实现规格」(ai4-tg3v) 交付了共享包 `sci-weave/shared/audit-trail`，写入面与查询面两张子票已关闭。但仓库里已有的审计实现一套都没接它，共享包实际是新增的第四套：

| 组件 | 审计表 | 定义 | 写入点 |
| --- | --- | --- | --- |
| research-map | `mapping_audit_event` | `schema.sql:44` | `candidate_submission.py:122` |
| research-wiki | `wiki_audit_event` | `schema.sql:26` | `sqlite_store.py:211` |
| task-agent gateway | `audit_events` | `gateway/mcp/src/gateway/store.py:36` | `gateway/mcp/src/gateway/app.py:35` |

三者字段名、字段集与主键类型都不同：`operation` / `action` / `event_type`；主键分别是 TEXT UUID、TEXT UUID、INTEGER AUTOINCREMENT。同一件事在审计链上有三种形状。

## Resolution

**结论：作用域分开，互不写入。** 本票提出的三处冲突与五个待裁决项，全部由「统一留痕的语义从『正式事实变更』改为『接口层对外调用』」一次性消解。共享包不再是领域审计的落地层，因此不存在「领域表接入共享包」这件事。

冲击本票的决策记录在 [中央服务留痕工具共享包实现规格](ai4-tg3v.md)（2026-10-22 改写），本票的五个 Q 逐条结案如下。

### Q1 领域表与共享表的关系 → 第四个答案：作用域分开

原设的三个选项（收敛 / 双写 / 投影）都假设两者记同一件事。改正语义后不是：

| 记录 | 记什么 | 谁来写 | 落哪 |
| --- | --- | --- | --- |
| 领域审计表 | 正式事实变更（谁在什么基准上改了什么、结果如何） | 领域服务在写事实的同一事务内 | 各领域自己的 SQLite |
| 中央审计账本 | 接口层对外调用（谁通过什么通道调了哪个工具、目标、结果、耗时） | MCP 接口层的装饰器 | 中央统一审计库 |

两者不重叠、不双写、不投影。领域表是**领域治理记录**，继续由领域自己在事务内写；中央账本是**访问账本**，只管接口层。跨两者的关联只靠 `target_object_id` 弱引用（账本记对象标识，不记对象历史）。

这解掉了「双写两个失败点」与「投影要维护同步」的全部代价——因为根本没有第二份。

### Q2 `operation` 枚举怎么扩 → 枚举整体删除

共享包不再有 `operation` 字段。领域代码继续用自己的值（`candidate_created`、`resource_version_review`、`resource_review_attempt`），不受影响。原判断「B 会把候选被创建塞进预审报告被追加」仍然成立，只是问题本身随字段删除而消失。

### Q3 同事务怎么落地 → 领域内保持现状，共享包不再要求

共享包删除 `conn.in_transaction` 校验，`TransactionRequiredError` 移除。领域侧现有的写入方式**不需要改**：

- map 侧 `candidate_submission.py:109` 的 `BEGIN IMMEDIATE` 一次写完事实与审计——保持。
- wiki 侧 `add_review()` 与 `add_audit_event()` 两次独立提交——**暂时保持**。这是 wiki 自身治理记录的一致性问题，属于领域内部质量，与中央账本无关，交由领域实现票自行决定是否收拢。本票不再以此作为阻塞项。

### Q4 `reason_code` 归属 → 留在领域表，Shared 表不再有对应字段

`wiki_audit_event.reason_code` 保持 `TEXT NOT NULL`，现有测试断言 `authority_missing` 不变。共享包不提供 `reason_code`，因为访问账本用的是 `error_code`（调用失败的可判代码），与领域审核结论的错误码是两个概念。

### Q5 字段改名谁负责 → 不必改名

`action`、`target_type`、`target_id`、`outcome` 都是领域表自己的字段，继续用。共享包用 `tool`、`target_object_type`、`target_object_id`、`result`，两套名字不冲突，因为不在同一张表。

### task-agent gateway

`audit_events`（`gateway/mcp/src/gateway/store.py:36`，`event_type`/`task_node_id`/`command_id`/`execution_id`，整数自增主键）保持现状。它是端侧执行遥测，`ai4-upsm` 已排除端侧；按 2026-10-22 决策，端侧执行过程追溯由 fast-agent-mcp 自身日志与 ExecutionRecord 状态机承担，不接中央账本。

## Acceptance Criteria

- [x] 三处冲突各有明确裁决，并写明依据
- [x] 两张领域审计表与共享 `audit_event` 的关系确定（结论为作用域分开，二者不重叠）
- [x] `operation` 枚举问题随字段删除消解，领域实际写入值不受影响
- [x] `reason_code` 留在领域表，wiki 现有断言 `reason_code` 取值的测试不受影响
- [x] 领域写入的事务形态无需为共享包改动，同事务约束从共享包移除
- [x] 端侧 `audit_events` 明确保持现状
- [x] 采纳结论回写到共享包规格票，并新开代码落地票

## Notes

**2026-10-22T10:30:00Z**

来源：审查共享包与现有领域实现时发现的冲突。依据仓库 ticket 属人规则，本票不改写 `ai4-6ljq`、`ai4-orpg` 名下内容，只作为关联票承载问题与待裁决项；落地方式与实现由对应地图负责人决定。

本票的审计对象是 `feature/qiyueran` 分支上 2026-10-22 的代码状态。若领域实现先于本票落地发生变化，事实部分以代码为准重新核对。

**2026-10-22T10:40:00Z**

已向 Gitee 提 issue 通知 hanjiang：[请 hanjiang 评估：Map 与 Wiki 接入统一审计留痕接口](https://gitee.com/qi-yueran/ai4science/issues/IKPL20)。正文含本票三处冲突与五个待裁决项，首行 @hanjiang。

操作说明：Gitee CLI 的 `issue comment` 端点返回 authentication failed（`issue create` 与 `issue edit` 正常），因此 @ 通知写在 issue 正文首行而非单独评论；Gitee CLI 也不支持设置 issue 负责人。

**2026-10-22T13:20:00Z**

结案。2026-10-22 与 Frank Qi 的 wayfinder grilling 把统一留痕的语义收窄为「接口层对外调用账本」，本票的前提（共享包是领域审计的落地层）随之消失，五个待裁决项按「作用域分开」一次结清，见 Resolution。

**对领域负责人的影响（不回写其票，仅在此记录）：**

- `ai4-6ljq`（Research Mapping 实现地图）与 `ai4-orpg`（LLM-Wiki 实现地图）**不需要**为接入共享包安排任何工作。领域审计表保持原样，无需迁移、改名、扩枚举。
- 若领域方希望自己的审计表与中央账本在查询上关联，用 `target_object_id` 弱引用即可，不需要结构改动。
- wiki 侧 `add_review()` 与 `add_audit_event()` 两次独立提交的问题**仍然存在**，但它现在是 wiki 自身的治理记录一致性问题，优先级由领域负责人判定，不再是中央留痕的阻塞项。
- 2026-10-22 10:40 那条 Gitee issue 通知的前提已不成立，需在对应 issue 下补充说明以免误导出结论的人。

**本票原「顺带」一节的两处包缺陷**已转入 [留痕包迁移到 centre-control 并改造为接口层调用账本](ai4-gvan.md)：`init_audit_table` 单语句 DDL 限制在改造中解决；README 示例的 `with conn:` 误写在改造中重写。另两处文档不一致（`occurred_at` 精度、`write_audit_event` 返回值）随写入接口重写而消失。
