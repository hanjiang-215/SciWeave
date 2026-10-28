# 中央 Agent 的预审判据

本文件是中央 Agent 预审判据的**权威文本**：四项检查依次查什么、冲突矩阵怎么算、失效怎么表达、混合候选什么时候才该做、分支事实怎么核。

它原先分散在 `toolkits/centre-agent-toolkit/` 的五个技能里（`prereview-checks`、`audit-candidate-branches`、`conflict-matrix`、`invalidation`、`merged-candidate`）。中央 Agent 是中央服务器上的一个**服务**，不是发给研究员的套件；套件退场（`ai4-0wg0`）后，这些判据并入 `docs/`，与定义层同受 Git 版本化。

## 三处文本，各管一段，不要互相复制

| 位置 | 谁读 | 写什么 |
| --- | --- | --- |
| `centre-agents/definitions/centre-prereview.yaml` 的 `instruction` | **模型**（运行时唯一能到达模型的文本，`skills=[]`） | 每一步做什么、能调什么、绝对不能做什么 |
| 本文件 | 人 | 判据本身：四项检查各查什么、边界在哪里、失败后归谁 |
| `centre-agents/rules/<version>.json` | 领域 MCP 与报告 | 只记版本号与 `checks` 名称清单；报告里记版本，领域侧据同一份文件解析 |

判据正文搬进本文件，**不是**搬进 `instruction`：把四项检查的全文抄进定义会让同一件事有两个版本，而它们漂移的表现是「报告写的版本领域侧解析不到」或「同一批候选在两种判据下结论不同」，从单侧看不出来。

## 一轮预审的输入是一次快照

```
list_reviewable_candidates(mapping_domain_id)      # 或 list_reviewable_wiki_candidates
```

一次调用返回该域**同一时点**的全量可送审候选：未放弃、未正式化、未驳回。每个候选带精确 `candidate_head`、`base_formal_revision_id`、正文快照与 `snapshot_status`。

- **一轮预审 = 一次调用 = 一批。** 不要逐条候选单独取，也不要多次调用再合并结果：冲突判定要求同批同时点，多拉一次会把两个前后脚提交的候选误判为不冲突。
- **不按基准版本过滤。** 基准过旧的候选照样纳入，只标 `stale`；Project Owner 需要在一处看到全貌。
- 正式版本发布会同时让一批候选的基准失配（见「失效判定」），那一轮要重拉。

## 第一步：核分支事实，不是先看内容

在「该不该进正式图」之前，先确认「这条分支是不是真的就是它声称的那条」。快照读不出来、head 对不上、来源说不清，后面所有判断都建在沙子上。

对每个候选按顺序核四件事实：

1. **`snapshot_status`**。不是 `available` 就没有正文。带 `reason_code` 时会给出 `candidate_store_unavailable`、`candidate_snapshot_missing`、`candidate_snapshot_digest_mismatch` 之类。**没有正文的候选一条结论都不能下**，包括「看起来没问题」——那是最危险的一种结论。
2. **`candidate_head`**。SQLite 里记录的精确 commit，领域 MCP 按它去 TerminusDB 读快照。它与 `candidate_commit_id`、`proposal_id`、`submission_id` 是四个不同的东西，汇报时不要混着说。
3. **`base_formal_revision_id`**。与当前正式版本比较，只影响 `stale` 这一列，不影响是否纳入本轮。空的基准在 Wiki 侧根本进不来（`formal_base_required`），在 Mapping 侧说明该域还没有任何正式版本。
4. **`submitter_id`**。以 `merged:` 开头的是混合候选，来源在 `change_set.merged_from` / `document_change` 的 provenance 里。它的「作者」不是一个人，别按单人候选去判权限。

`candidate_snapshot_digest_mismatch` 只可能在这一步被发现：创建候选时算过一次摘要，预审时按精确 commit 再读一次。两者不一致说明存储里的内容变了——**不要修候选，也不要重算摘要**，把 `reason_code` 原样写进检查项，让提交方重提。

`prereview_status` 的三个状态是每轮的第一件事：`missing_report`（从没预审过）、`report_current`（最新结论对这一 head 有效）、`report_stale`（已被判定失效）。一条 `report_stale` 的候选即使内容看起来完美，也还不该被送去裁决。

分界很清楚：这一步回答「能读吗、对得上吗」，下一步回答「内容对不对」。**不能读就不要往下走**；把「读不出来」写成 `verdict=failed` + 原样的 `reason_code`，比假装它通过要好——Project Owner 看到 failed + 存储原因会去修存储，看到 passed 会去批准一个没人读过的东西。

## 第二步：四项检查

格式、对象引用、依赖关系三项**在领域 MCP 写入候选时就被拒绝**（`invalid_change_set`、`invalid_task_node`、`invalid_dependency_edge` 等），所以输入永远是干净候选。不要重复实现这三项，也不要把「格式对不对」写进报告——那只会让报告看起来更全面。

| 检查 | 输入 | 判定 | 失败后 |
| --- | --- | --- | --- |
| 权限范围 | `submitter_id` 与目标单元的 `task_owner_id` / `created_by` | 两者都对不上即失败 | 报告事实；补授权不是中央 Agent 的事 |
| 基准版本 | `base_formal_revision_id` vs 当前正式版本 | 不相等即 `stale` | 报告事实，不改 Proposal 状态 |
| 冲突 | 同批候选在同一逻辑对象上的改动 | 重叠即 `conflict` | 报告事实，须由提交方出新候选解决 |
| 影响范围 | 从不可调度变可调度、受影响的资源引用 | 说不清影响即不通过 | 报告事实 |

两条判定的具体口径：

- **权限范围只按 `submitter_id` 判，不要假想有一张权限表。** 领域侧没有暴露「谁能改哪个单元」的查询：能判的只有 `submitter_id` 是否等于目标节点的 `task_owner_id` 或 `created_by`。两者都取不到时不要猜，也不要当成通过——判失败，`reason_code` 写 `permission_evidence_unavailable`，并在 `evidence_summary` 里说明缺哪个字段。
- **影响范围只看「从不可调度变可调度」与资源引用。** 不要声称能核对受影响的执行记录：那不在可读范围内，写进去就是编。

`stale` 与 `conflict` 是**报告里的事实列，不是 Proposal 状态**。中央 Agent 不改候选、不改 Proposal、不建 Merge Request Buffer；候选怎么处置由 Project Owner 在批准或驳回时决定。

## 第三步：冲突矩阵

冲突判定是**同批、同时点**的事。逐个候选判不冲突、合起来却是两个候选改同一个 `logical_id`——这就是矩阵存在的唯一理由。

**Mapping**：对象身份是 `logical_id`（`TaskNode` 与 `DependencyEdge` 都有）。同一个 `logical_id` 的两个不同 `version_id` 被两个候选同时改动就是冲突——不是因为内容不同，而是因为两条分支都想成为它在正式图里的下一个版本。注意每个 node 的 `@id` 是 `TaskNode/<version_id>`，所以「同一逻辑对象」必须按 `logical_id` 归并；按 `@id` 或 `version_id` 归并会让同一个对象的两个候选被当成两个对象，冲突永远判不出来。

**Wiki**：对象身份是 `document_id`，一次改动落在一个 `WikiRevision` 上。两候选改同一个 `document_id` 即为冲突。引用（`ResourceReference`）不是冲突主体，但指向同一资源版本的两处不同说法应在 `overlap` 里说明。

写进报告时**两侧都要写**：

```json
[
  {"candidate_id": "cand-a", "overlap": "TaskNode/logical-7: also changed by cand-b"},
  {"candidate_id": "cand-b", "overlap": "TaskNode/logical-7: also changed by cand-a"}
]
```

只写一侧会让读报告的人以为另一条候选是干净的。`overlap` 是一句人能读懂的说明，不是机器可解析的格式——真正需要机器比较的是 `checks` 里的条目。

三个容易越界的点：

- **冲突是事实，不是裁决。** 只报告「这两条在 `logical_id=...` 上重叠」，不选谁对、不合成第三条、不改任何一条。解决冲突必须由提交方出新候选，或由 Project Owner 指定其中一条。
- **入边消失不是冲突。** 一条候选删掉某个节点的入边会让它从「不可调度」变「可调度」，那是影响范围，不是冲突。
- **跨域不成批。** Mapping 与 Wiki 的候选永不在同一批里，一次 `append_prereview_log` 只写一个域。这不是遗漏，是设计。

## 写结论

```
append_prereview_log(
  mapping_domain_id="...",            # Wiki 侧是 wiki_domain_id
  candidate_id="...", candidate_head="...",
  base_formal_revision_id="...",
  rule_set_version="1.0.0",
  verdict="passed" | "failed",
  checks=[{"name": "...", "verdict": "passed|failed", "reason_code": "...", "evidence_summary": "..."}],
  conflict_matrix=[{"candidate_id": "...", "overlap": "..."}],
)
```

- **只追加。** 同一 `(candidate_id, candidate_head, rule_set_version, base_formal_revision_id)` 重复调用返回上一条（`duplicate=true`），不是失败，是幂等。
- **`checks` 不能为空数组**，每条至少要有 `name` 与 `verdict`。
- `verdict=passed` 只表示「可以送 Project Owner 选择」，**不表示批准**；汇报时不要把 `passed` 说成「通过了」。
- 报告必须带 `rule_set_version`，并且这个版本要能在 `SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR` / `SCIWEAVE_WIKI_PREREVIEW_RULES_DIR` 里解析到一个 `<version>.json`（至少含 `version` 与 `checks`）。解析不到时 `append_prereview_log` 返回 `rule_set_missing`——不要改成随便一个版本号重试。
- 结论落库之后才发 `prereview_completed` 通知。顺序反了，Project Owner 会收到一条「已预审」但日志里查不到的提醒，那比不通知更糟。通知里只放结论、候选 id 与 head、以及需要他决定的事，不要抄正文。

## 失效判定

一份预审报告只在两个时点仍然成立时有效：产生它的 `candidate_head` 与 `base_formal_revision_id`。任一移动，报告即失效。失效的表达方式只有一种：**追加一条判定**，历史报告一个字不动。

| `reason` | 什么时候 | 额外要求 |
| --- | --- | --- |
| `head_moved` | 候选有了新 head，旧报告对应的是旧内容 | 必须带 `superseding_report_id`，指向新 head 上那份报告 |
| `base_moved` | 正式版本发布了，候选的基准变成旧版本 | 不需要 superseding；重算完成前该候选卡住 |

- `head_moved` 不带 `superseding_report_id` 会被拒（`invalid_arguments`）。没有新报告的「失效」等于让候选既没有有效报告也没有下一步，那是把门禁变成黑洞。
- 目标候选 head 上**没有任何当前报告**时返回 `report_not_found`。这不是让你补一条报告，而是说明这条候选本来就该走一次正常预审。
- **失效 ≠ 放行。** 门禁是硬的：没有当前报告的候选不能被批准，没有例外。
- **失效 ≠ 冻结全体。** 粒度是单个候选：`base_moved` 只影响基准与刚发布版本不同的候选，基准正好等于新版本的候选完全不受影响。

**触发方是 `gateway/ingest`，不是 Agent 自己。** 收到 `formal_revision_published` 时，对每个基准与它不同的候选、若当前状态是 `report_current`，追加一条 `base_moved` 并列为需要重算；收到 `candidate_created` / `candidate_head_updated` 时按窗口去抖后触发一次全量快照重审（默认 60 秒窗口；一轮预审覆盖全量候选，所以同一窗口里多次 head 更新只值一次重算）。实现见 `centre-agents/gateway/ingest/src/gateway_ingest/service.py`。

手工补录只在一种情况下用：ingest 停了半天、事件被跳过，事后发现某个候选的报告明明不该算数却还是 `report_current`。补录前先确认报告的 `candidate_head` 与候选当前 head 确实不同，否则你会把一条有效报告判成失效。

## 混合候选

混合候选是**一条普通候选**：同一套预审、同一个 Project Owner 批准路径，不引入新的 Proposal 状态。它唯一特殊的地方是来源不止一个。

**混合解决的是分工，不是冲突。**

- 候选 A 改 `TaskNode/logical-3`，候选 B 改 `TaskNode/logical-8`，两条都单独可送审——合成一条能让 Project Owner 一次看到完整的一步推进，该混合。
- 候选 A 与 B 都改 `TaskNode/logical-3` 且版本不同——这是冲突。混合会把两个互相矛盾的版本塞进一个分支，让一条候选里出现两套说法：该由提交方出新候选，或由 Project Owner 选一条。

判断依据就是冲突矩阵：`conflict_matrix` 里出现同一 `logical_id` 就不该混合。不要在混合之后让人去发现冲突。

```
create_merged_candidate(
  mapping_domain_id="...",
  source_proposal_ids=["prov-a", "prov-b"],
  base_formal_revision_id="...",
  change_set={...},
  idempotency_key="merge-<digest>",
)
```

三条硬约束：

1. **只新建。** 源候选永不被编辑；混合产生新分支，源候选原样留着。
2. **作者是多值的。** 服务端把 `submitter_id` 写成 `merged:<hash(sorted 源作者)>`，并把每个源的 `proposal_id`/`submission_id`/`submitter_id` 写进 `change_set.merged_from`。**源作者对这条混合候选没有任何操作权**——不能改它、不能替代它，也不能用它覆盖自己的源候选。
3. **不得二次混合。** 源作者以 `merged:` 开头时直接返回 `nested_merged_candidate`。混合一条已混合过的候选等于把 provenance 压成一层，之后没人能追出原始作者。

其他服务端拒绝：`source_candidate_not_found`（`proposal_id` 不属于这个域）、`source_candidate_not_reviewable`（源状态不是 `candidate` / `review_pending` / `approved_pending_formalization`）、`nested_merged_candidate`、`invalid_change_set` / `invalid_task_node`（合成后的正文没过机械校验）。

源候选必须都在**同一个正式基座**上——`base_formal_revision_id` 是单一值。跨基座的候选不能混合：它们的差异里已经混进了两个正式版本之间的变化，合成后就说不清哪部分是候选带来的。

混合之后与普通候选完全一样：跑一遍预审（四项检查）、报告里点明它来自哪几条源候选、通知仍用 `prereview_completed`，不另造通知类型。

## 尚未接通的部分

本文件的判据已经写定，但下面两块在**当前实现**里还没有调用方，不要把它们当成已可用：

| 判据 | 现状 |
| --- | --- |
| 混合候选 | 卡片里有 `create_merged_candidate`（`centre-agents/libs/mcp-libs/research-{mapping,wiki}/mcp.json`），但五步 Chain 里没有任何 agent 的 `allowed_tools` 包含它，也没有定义调用时机（`ai4-8dgd` 只定了写面与作者归属） |
| 失效判定 | 由 `gateway/ingest` 自动追加，不由 Agent 调用；`append_prereview_log` 的 `reason` 分支只在补录时手工用 |

`centre-agents/rules/1.0.0.json` 的 `checks` 只列四项检查的名称，不含本文件的正文；这与「只记版本号与检查项清单，不记提示词全文」一致。

## 边界

中央 Agent 读得到所有域的候选，但**一个都不能批**。它不写正式图、不改已有候选、不进草稿箱、不派发任务、不判断「下一步该谁动」、不修源候选、不改历史报告、不二次混合、不一次调用同时改两个域。

批准是 Project Owner 的动作：`formalize_candidate` / `formalize_wiki` / `decide_wiki_review` / `record_review` 都不在中央侧任何一张卡片里。
