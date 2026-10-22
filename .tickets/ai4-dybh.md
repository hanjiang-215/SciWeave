---
id: ai4-dybh
status: open
deps: []
links: [ai4-tg3v, ai4-ze1x, ai4-rh97, ai4-upsm]
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

`task-agent` 那套属于端侧执行遥测，`ai4-upsm` 的 Resolution 已明确端侧不是共享包的调用方，不在本票范围内（但见下方「顺带」一节）。本票只处理中央侧的 map 与 wiki。

本票不是实现票：两张领域表归 `ai4-6ljq`（Research Mapping 实现地图）与 `ai4-orpg`（LLM-Wiki 实现地图）的负责人，本票只承载「要不要收敛、怎么收敛」的决策与待裁决的冲突事实。按仓库属人规则，本票未与那两张票建立双向 `links`（那会改动它们的 frontmatter），改以正文引用；两个地图的负责人看到本票后自行决定是否采纳，并由其在票内建立关联。

## 三处必须先裁决的冲突

三处都有可复现证据，任一条不定，接入都会失败。

### 1. `operation` 枚举盖不住领域已在写的值

共享枚举首版 5 个，全是「预审 / 正式化」视角：

```text
draft.status_changed
mapping.prereview_log_appended
mapping.formal_revision_promoted
wiki.prereview_log_appended
wiki.formal_revision_promoted
```

而领域代码现在实际写入的值是：

| 组件 | 实际值 | 出处 |
| --- | --- | --- |
| research-map | `candidate_created` | `candidate_submission.py:123` |
| research-wiki | `resource_version_review` | `resource_review.py:171` |
| research-wiki | `resource_review_attempt` | `resource_review.py:295` |

三个值都不在枚举内。`research-map` 一旦接入，第一次写就抛 `AuditValidationError`。

### 2. `reason_code` 无处安放

`wiki_audit_event` 有三个共享表没有的字段：`reason_code TEXT NOT NULL`、`detail`、`related_review_id`。

`detail` 与 `related_review_id` 可以进 `refs` JSON，`reason_code` 不行——它是数据库层的 `NOT NULL` 约束，`refs` 兜不住。而且 `reason_code`（机器可判的错误码，如 `authority_missing`）与共享表的 `reason`（人写的说明文字）是两个概念，合并会丢信息。

`wiki` 现有测试直接断言 `reason_code` 的值（`tests/test_resource_review.py` 断言 `authority_missing`），改名或降级为自由文本会打破这些断言。

### 3. 「同事务」约束当前无法满足

共享包的核心约束是「留痕与事实写在同一个 SQLite 事务里」，实现方式为校验 `conn.in_transaction`。

但 wiki 侧现在是两次独立提交、两条不同连接：

- `sqlite_store.py:45` 的 `add_review()` 自带 `connection.commit()`
- `sqlite_store.py:207` 的 `add_audit_event()` 是另一个函数，也自带 `commit()`
- `resource_review.py:168-181` 先后调这两个
- `sqlite_store.py:36` 的 `connection()` 是生成器，每次新建连接再关闭

map 侧相反，是对的：`candidate_submission.py:109` 用 `BEGIN IMMEDIATE` 在一条连接里写事实与审计。但它只写 `mapping_audit_event`，没走共享包。

即：这个约束对 wiki 侧是结构性改动，不是加一行调用能解决的。

## 需要裁决的问题

### Q1 领域表与共享表的关系

- **A 收敛**：领域表退役，只留共享 `audit_event`；领域专属字段进 `refs`，`reason_code` 提为共享表可选列。
- **B 并存双写**：一次事实写两条审计。
- **C 投影**：领域表是事实源，共享表在写入时同步派生。

建议 A。B 让每次写入有两个失败点，且「哪个是真的」永远说不清；C 要维护同步机制，比双写更容易出错。A 的代价是重构 wiki 的连接管理和 map 的写入路径，但两个领域都还没接真实写入方，现在改最便宜。

### Q2 `operation` 枚举怎么扩

- **A 按事实源扩**：补 `mapping.candidate_created`、`wiki.resource_version_review`、`wiki.resource_review_attempt`。
- **B 只留 5 个**：领域把值映射到最接近的枚举。
- **C 去掉枚举**：`operation` 改自由文本加命名约定。

建议 A。B 会把「候选被创建」塞进「预审报告被追加」，两件事再也分不开——而分开追溯正是这个包存在的理由；C 放弃的正是枚举带来的那点约束。

### Q3 同事务怎么落地

- **A 重构领域写入**：事实写与审计写合成一次连接生命周期。
- **B 放宽为同连接独立提交**。
- **C 由包接管事务**：包提供带连接的写入上下文。

建议 A。这是共享包唯一真正的价值——把「改了事实没留痕」变成不可能。B 等于放弃这条保证；C 让包伸手进调用方的事务边界。

### Q4 `reason_code` 归属

- **A 提为共享表可选列**。
- **B 进 `refs`，wiki 侧去掉 `NOT NULL`**。
- **C 与 `reason` 合并**。

建议 A。

### Q5 字段改名谁负责

`action`→`operation`、`target_type`→`target_object_type`、`target_id`→`target_object_id`、`outcome`→`result`。

- **A 领域代码改用共享命名**。
- **B 共享包提供别名适配层**。

建议 A。同一概念两套名字，长期一定有人用错；`WikiAuditEvent` 是本地的 dataclass，改名只影响自身代码与测试，面可控；适配层则是给错误命名发长期通行证。

## Acceptance Criteria

- [ ] 三处冲突各有明确裁决，并写明依据
- [ ] 两张领域审计表与共享 `audit_event` 的关系确定（收敛 / 并存 / 投影 三选一）
- [ ] `operation` 枚举覆盖两个领域实际写入的全部值，或给出可机械执行的映射
- [ ] `reason_code` 有明确归属，且 wiki 现有断言 `reason_code` 取值的测试仍通过
- [ ] 事实写入与留痕写入在同一 `sqlite3.Connection` 的同一事务内完成，并有回归测试证明独立调用被拒
- [ ] 迁移后按目标与时间检索的能力不丢失，结果与迁移前一致
- [ ] 采纳结论回写到 `ai4-6ljq` 与 `ai4-orpg` 的地图负责人，由其决定落地票

## 关联

双向关联自 `ai4-tg3v` / `ai4-ze1x` / `ai4-rh97` / `ai4-upsm` 建立（见本票 `links`）。`ai4-6ljq` 与 `ai4-orpg` 按属人规则未建双向链接，只在本票正文引用其 id；是否需要关联由那两张票的负责人决定。

## 顺带：共享包自身的两处缺陷

这两条不涉及领域归属，由 `ai4-tg3v` 那条线自己收，列在这里避免遗漏：

1. **`init_audit_table` 只支持单语句 DDL**。`writer.py:29` 用 `conn.execute(_SCHEMA_SQL)`，`schema.sql` 目前只有一条 `CREATE TABLE` 所以能跑；一旦加索引就抛 `ProgrammingError: You can only execute one statement at a time`（已实测）。
2. **README 示例跑不通**。`README.md` 示例写 `with conn: write_audit_event(conn, event)`，但 `with conn:` 只在退出时提交、进入时不开启事务，`sqlite3` 只在第一条 DML 执行时才隐式 `BEGIN`。照抄必抛 `TransactionRequiredError`（已实测）。正确写法是先 `conn.execute("BEGIN")`。

另有两处文档不一致（同样归 `ai4-tg3v`）：

- `ai4-tg3v` 写 `occurred_at` 为**秒精度**，实现是微秒（`writer.py:62` 用 `timespec="microseconds"`），`ai4-ze1x` 的 Notes 也写微秒。
- `ai4-upsm` 写 `write_audit_event(...) -> None`，实现返回 `event_id`（`writer.py:41` 返回 `str`），测试依赖这个返回值。

## Notes

**2026-10-22T10:30:00Z**

来源：审查共享包与现有领域实现时发现的冲突。依据仓库 ticket 属人规则，本票不改写 `ai4-6ljq`、`ai4-orpg` 名下内容，只作为关联票承载问题与待裁决项；落地方式与实现由对应地图负责人决定。

本票的审计对象是 `feature/qiyueran` 分支上 2026-10-22 的代码状态。若领域实现先于本票落地发生变化，事实部分以代码为准重新核对。

**2026-10-22T10:40:00Z**

已向 Gitee 提 issue 通知 zhanyunfei：[请 zhanyunfei 评估：Map 与 Wiki 接入统一审计留痕接口](https://gitee.com/qi-yueran/ai4science/issues/IKPL20)。正文含本票三处冲突与五个待裁决项，首行 @zhanyunfei。

操作说明：Gitee CLI 的 `issue comment` 端点返回 authentication failed（`issue create` 与 `issue edit` 正常），因此 @ 通知写在 issue 正文首行而非单独评论；Gitee CLI 也不支持设置 issue 负责人。
