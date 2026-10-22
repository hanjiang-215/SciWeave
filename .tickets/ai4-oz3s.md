---
id: ai4-oz3s
status: closed
deps: []
links: [ai4-he04, ai4-5z9e, ai4-oebi, ai4-rlv6, ai4-a2ba, ai4-8dgd, ai4-t2wc]
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

报告写入**领域治理记录**，与候选、Proposal 的治理记录同库——即领域自己的 SQLite（`research-map` 与 `research-wiki` 各一个库文件，均使用 `sqlite3` 与 `executescript` 建表）。不新建第三个库，也不写进中央审计账本。

**两套领域库各一张表，不建跨领域共享表。** 字段逐列对齐，DDL 各自由领域维护：

| 领域 | 报告表 | 失效判定表 |
| --- | --- | --- |
| Research Mapping | `mapping_prereview_report` | `mapping_prereview_report_decision` |
| LLM-Wiki | `wiki_prereview_report` | `wiki_prereview_report_decision` |

不共享一张表的原因：两个领域是隔离的部署边界，表要能被各自的 schema 与迁移独立演进；共享表会把一个领域的字段变更变成另一个领域的破坏性变更。

**冲突矩阵只在同一领域内比较。** 跨领域不构成对象冲突——`research-map` 的路径节点与 `research-wiki` 的文档之间没有「同一逻辑对象」这个关系。因此每张报告表的 `conflict_matrix` 只引用同领域的候选 ID，实现时不需要、也不应该去建一张跨领域的对照表。

中央 Agent 对领域 MCP 的写入面只有两个工具，且分开授权：

| 工具 | 用途 | 约束 |
| --- | --- | --- |
| `append_prereview_log` | 追加一份预审报告或一条失效判定 | 只追加，不可改、不可删 |
| `create_merged_candidate` | 新建混合候选分支 | 只能新建，不改动已有候选 |

写预审日志与写领域内容是两类不同的权限。合成一个工具等于让「能读候选」的凭据顺带获得「能改候选内容」的能力。

### 表结构

契约层面的 DDL 骨架（Mapping 侧；Wiki 侧只换表名前缀）：

```sql
CREATE TABLE IF NOT EXISTS mapping_prereview_report (
    report_id               TEXT PRIMARY KEY,
    candidate_id            TEXT NOT NULL,
    candidate_head          TEXT NOT NULL,
    base_formal_revision_id TEXT,
    rule_set_version        TEXT NOT NULL,
    checks                  TEXT NOT NULL,
    verdict                 TEXT NOT NULL CHECK (verdict IN ('passed', 'failed')),
    conflict_matrix         TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    UNIQUE (candidate_id, candidate_head, rule_set_version)
);

CREATE TABLE IF NOT EXISTS mapping_prereview_report_decision (
    decision_id           TEXT PRIMARY KEY,
    target_report_id      TEXT NOT NULL,
    reason                TEXT NOT NULL CHECK (reason IN ('head_moved', 'base_moved')),
    superseding_report_id TEXT,
    decided_at            TEXT NOT NULL,
    CHECK (reason <> 'head_moved' OR superseding_report_id IS NOT NULL),
    FOREIGN KEY (target_report_id) REFERENCES mapping_prereview_report (report_id),
    FOREIGN KEY (superseding_report_id) REFERENCES mapping_prereview_report (report_id)
);
```

`checks` 与 `conflict_matrix` 存 JSON 文本（SQLite 无原生数组类型），两者的元素形状由「中央 Agent 候选预审检查项与失败处置」(ai4-5z9e) 定义，本票只定它们是数组、不含判据正文。

两张表都没有 `UPDATE` / `DELETE` 语句，接口层也不提供对应函数。唯一键走 `INSERT ... ON CONFLICT DO NOTHING` 后 `SELECT`，天然返回首次报告。

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
| `conflict_matrix` | 与同批其他候选在同一逻辑对象上的冲突关系（仅同领域） |
| `created_at` | 生成时间 |

唯一键为 `(candidate_id, candidate_head, rule_set_version)`：同一候选同一 head 用同一版判据重审，返回首次报告，不产生第二份结论。这条同时替代了原先设想的分发租约——单实例常驻，重放靠幂等而非互斥。

**`superseded_by` 已从报告里删除**（2026-10-22 修订）。它要表达的是「这份报告被取代了」，而写这个字段就是编辑一条既有报告，与只追加冲突。取代关系改由失效判定表承载，见下节。

### 追加与不可修改

日志是事实记录，不是工作区。同一候选出现新 head 时产生**新的**报告条目。不提供编辑或删除入口，包括对中央 Agent 自己。

**失效用追加的判定条目表达，不改旧报告**（2026-10-22 修订）。旧正文写「旧报告标 `stale`」「标 `superseded_by`」，这两种写法都是对既有行的一次编辑，与只追加直接矛盾。改为向判定表追加一条记录，旧报告一个字不动：

| 触发 | 追加的判定 | 判定字段 |
| --- | --- | --- |
| 候选头移动 | 一条 `reason='head_moved'` | `superseding_report_id` 指向新 head 的报告 |
| 基准正式版本移动 | 一条 `reason='base_moved'` | `superseding_report_id` 为空，直到重算完成再由 `head_moved` 或新报告收尾 |

「某份报告现在是否有效」由**追加的判定推出**，不落在报告行上：对同一 `candidate_id` 取其所有判定中 `decided_at` 最新的一条，若它指向该报告则报告已被取代，否则该报告仍是当前结论。查询形状是 `ORDER BY decided_at DESC, rowid DESC LIMIT 1`。

判定表同样只追加：不提供判定条目的撤销。判定错了就再追加一条把方向改回来，历史里两条都留着。

被 `base_moved` 判定的报告仍在日志里，但它不能作为批准依据：受影响候选在重算完成前卡住，未受影响的候选照常可批。是否失效不改 Proposal 状态——它是报告侧的一次判定，不是对候选的处置。

### 判据版本化

`rule_set_version` 只记版本号和检查项清单，不记提示词全文。规则文件本身受 Git 管理，报告的结论要与当时的规则一致。这样事后能判断两次结论的差异来自候选变化还是判据变化。

**规则文件的位置与内容不在本票范围。** 由「中央 Agent 能力接口收口」(ai4-rlv6) 决定规则文件落在 `docs/` 下的哪个路径并写出首版内容；本票只要求 `rule_set_version` 是一个可追溯的字符串版本号，且报告里存一份**检查项名清单**，使「当时的判据包含哪些检查」在规则文件缺失时仍可判读。

规则文件缺失或版本号无法解析时，`append_prereview_log` 必须失败并返回 `rule_set_missing`，不写一份无据可查的报告。写一份说不清依据的报告，比没有报告更难排查。

### 与 Proposal 状态的关系

报告只提结论，不改 Proposal 状态。`verdict`（通过/不通过）与 `conflict_matrix` 里的冲突项是报告里的事实，由 Project Owner 在批准或驳回时处置。中央 Agent 不改写候选、不改 Proposal 状态、不建 Merge Request Buffer。

领域 `mapping_proposal.status` / Wiki 侧对应的正式化状态取值不因本票增加。`stale` 是报告侧的失效判定，不是 Proposal 状态。

## Acceptance Criteria

- [x] 报告字段完整，且不含判据全文，只含 `rule_set_version` 与检查项名清单
- [x] 两套领域库各一张报告表与一张判定表，字段对齐但 DDL 各自维护，不建跨领域共享表
- [x] 冲突矩阵只比较同领域候选，跨领域不构成冲突
- [x] 唯一键为 `(candidate_id, candidate_head, rule_set_version)`，重复审同一对象返回首次结论
- [x] 日志只追加：两张表都无 `UPDATE` / `DELETE` 语句，接口层不提供编辑与删除入口
- [x] 候选头移动时追加 `head_moved` 判定并带 `superseding_report_id`，旧报告行不被修改
- [x] 基准正式版本移动时追加 `base_moved` 判定、`superseding_report_id` 为空，重算完成前该候选卡住
- [x] 「当前有效报告」由最新一条判定推出，查询按 `decided_at DESC, rowid DESC` 取首条
- [x] 写报告与新建混合候选是两个独立工具，权限可分开配置
- [x] `rule_set_version` 无法解析到规则文件时 `append_prereview_log` 返回 `rule_set_missing` 并拒绝写入
- [x] 报告不修改 Proposal 状态、不写正式版本、不建 Merge Request Buffer
- [x] 报告由领域管理 MCP 写入领域治理记录，该次对外调用由中央留痕账本记录；中央 Agent 无私有审计通道
- [x] 有回归测试覆盖重复审同一 head、候选头变化后新旧报告并存、旧报告行字节不变
- [x] 有回归测试覆盖正式版本发布追加 `base_moved` 判定、未受影响候选的报告仍有效

## Notes

**2026-10-21T23:40:00Z**

来源：2026-10-21 第五轮讨论。用户裁决「有写权限，可以类似日志的方式保存」。

本票承接「中央 Agent 候选预审入口与结论回写」(ai4-he04) 中「结论写回领域治理记录」一项的形态定义。he04 负责入口与失效判定，本票负责存储形态。

**2026-10-22T09:20:00Z**

2026-10-22 补充：新增可选字段 `superseded_by`；把「被取代的两种原因」写进正文——候选头移动产生新报告并指向它，基准正式版本移动只标 `stale` 且不指向新报告。相应新增两条验收。依据 Project Owner 2026-10-22 裁决「stale 后重算，重算期间该候选卡住」。

**2026-10-22T14:50:00Z**

2026-10-22 下午经 wayfinder grilling 收口，三项裁决：

1. **失效改为追加判定条目**（原「给旧报告标 `stale` / 写 `superseded_by`」作废）。那两种写法都是编辑既有行，与正文自己写的「不提供编辑入口」直接矛盾。改为独立的判定表，旧报告只读。`superseded_by` 字段随之删除。
2. **两套领域库各一张表**，不共享。理由是两个领域是隔离的部署边界，表要能各自演进；共享表会把一方的字段变更变成另一方的破坏性变更。冲突矩阵因此只在同一领域内比较。
3. **`rule_set_version` 的文件位置不在本票定**，交由「中央 Agent 能力接口收口」(ai4-rlv6)；本票只要求规则缺失时拒写并返回 `rule_set_missing`。

同时修正一处过期验收：`报告经留痕工具写入同事务审计` 改为 `由领域管理 MCP 写入领域治理记录，该次对外调用由中央留痕账本记录`。同事务约束已随「中央服务留痕工具」的 2026-10-22 修订作废，接口层账本与领域存储是两个库，跨库没有原子提交。另修正报告字段表里一处笔误 `/| created_at`。

「与 Proposal 状态的关系」一节不再用 `stale` 这个词指代 Proposal 状态取值，避免与判定表的 `base_moved` 混用。
