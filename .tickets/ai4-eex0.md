---
id: ai4-eex0
status: closed
deps: []
links: [ai4-5z9e, ai4-he04]
created: 2026-10-21T15:36:52Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-fv1r
tags: [centre-agents, mapping, wiki, prereview, wayfinder:grilling]
---
# 候选创建的机械校验前置

把格式、对象引用、依赖环、基准版本比对四项确定性检查前移到领域管理 MCP 创建候选时，让脏数据进不了候选分支，中央 Agent 只承担需要判断的检查。

## Question

哪些预审检查由领域 MCP 在写入时就拒绝，哪些留给中央 Agent；这项拆分的依据与后果是什么。

## Design

### 拆分依据

判定完全由规则给出、不需要看语义的检查，代码做得比模型可靠，也能在写入那一刻就拦住。留在中央 Agent 的只有需要跨候选或跨领域比较、或需要解释影响的那部分。

| 检查 | 现在的归属 | 理由 |
| --- | --- | --- |
| 格式与结构 | 领域 MCP 写入时拒绝 | 按领域 schema 校验，确定性 |
| 对象引用 | 领域 MCP 写入时拒绝 | 目标存在性可查，确定性 |
| 依赖关系（自环、blocking 环、端点版本） | 领域 MCP 写入时拒绝 | 图算法，确定性 |
| 基准版本比对 | 领域 MCP 写入时拒绝 `base` 不存在的情况；**是否等于当前正式版本仍由中央 Agent 判定** | 「基准过旧」不影响写入合法性，只影响能否送审 |
| 权限范围 | 中央 Agent | 需要跨主体意图判断，不是单条记录的格式问题 |
| 同一逻辑对象上的冲突 | 中央 Agent | 需要同批多候选的快照比对 |
| 影响范围 | 中央 Agent | 需要解释，无法由规则给出 |
| 混合方案 | 中央 Agent | 生成行为，不是校验 |

### 后果

1. **中央 Agent 的输入永远是干净的**：它读到的候选一定格式合法、引用存在、无环。因此 `ai4-5z9e` 里的「格式失败」「引用失败」「依赖失败」三个状态在中央 Agent 侧不再出现，它们变成领域 MCP 的写入错误码。
2. **`abandoned` 状态少了一部分来源**：原设计里结构或权限失败映射为 `abandoned`。结构失败不再进候选，`abandoned` 只剩权限失败一类。这不改变 Proposal 状态取值，只改变谁产生它。
3. **两个 MCP 都要改**：`centre-control/research-map` 与 `centre-control/research-wiki` 的候选创建路径都要补这层校验。`research-map` 已有候选提交模块，改动落在那里而不是新写一遍。

### 不改变的部分

域 MCP 只做「能不能写入」的判断，不做「该不该批准」的判断。写入合法与可以送审是两件事：一个格式完全合法的候选可能语义上冲突，那仍然由中央 Agent 报给 Project Owner。

## Acceptance Criteria

- [x] 四项机械检查在领域 MCP 的候选创建路径上拒绝非法输入，并有明确错误码
- [x] 基准版本「等于当前正式版本」仍作为预审判定，不在写入时拒绝
- [x] 中央 Agent 的检查表相应缩减，不再包含格式、引用、依赖三类
- [x] 明确「写入合法」与「可以送审」是两个不同判断
- [x] 两套领域 MCP 的校验行为一致，不一套严一套松
- [x] 有回归测试覆盖每种被拒绝的输入

## Notes

**2026-10-24 关闭验收（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

2026-10-24 复跑验证关闭：research-map 全量 95 项通过（5 跳过真实 TerminusDB 集成）、research-wiki 全量 102 项通过（4 跳过），0 失败，与 Notes 实现记录一致。六项验收全部勾选。检查表缩减已同步到 `ai4-5z9e`（该票 assignee 已接受重排）。本票关闭。

**2026-10-24 eex0 实现与验收（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

按 2026-10-21 第五轮拆分结论实现：格式、对象引用、依赖环三项机械校验继续在领域 MCP 候选创建路径拒绝（research-map 的 `_validate`、research-wiki 的 `_valid_document`/`_validate_references` 已覆盖）；本次把「基准版本比对」从写入时拒绝拆为两个判断：

- `base_formal_revision_id` 缺失 → 写入时拒绝，稳定错误码 `formal_base_required`（两领域一致）。
- base 引用的正式版本不存在或域不符 → 写入时拒绝，新增稳定错误码 `base_revision_missing`（两领域一致）。
- base 存在但不等于当前正式版本 → **不再写入时拒绝**；候选照常进入候选分支，`stale` 由中央 Agent 预审报告判定（对应 ai4-5z9e 预审检查表与 ai4-a2ba 门禁）。

对应代码：`candidate_submission.py`（两领域）把原 `stale_base` 写入拒绝拆分；`_persist` 的并发检查从「current == base」改为「base revision 仍存在」。正式化端（formalization/review）的 `stale_base` 语义不变：Owner 正式化仍要求 current == candidate.base，旧 base 候选送审时按 stale 处理，与 ai4-iciy 重放治理一致。

验证：

- research-map：`uv run --locked python -m unittest discover -s tests -q` → 91 项通过、5 项跳过（真实 TerminusDB 集成）、0 失败。
- research-wiki：`uv run --locked python -m unittest discover -s tests -q` → 98 项通过、4 项跳过、0 失败。
- 新增回归测试：mapping（基于旧 base 写入成功、base 不存在拒绝、写期间 formal 指针前进仍持久化）、wiki（base 缺失 `formal_base_required`、base 不存在 `base_revision_missing`、origin 早于当前 base 写入成功）。
- 未新增依赖，未提交远程。

「中央 Agent 的检查表相应缩减」已作为 assignee 裁决并更新到「中央 Agent 候选预审检查项与失败处置」(ai4-5z9e)。

**2026-10-21T23:40:00Z**

来源：2026-10-21 第五轮讨论。用户裁决「对」——机械检查前移到领域 MCP。

与「中央 Agent 候选预审检查项与失败处置」(ai4-5z9e) 的关系：本票缩减它的检查表，由该票负责人裁决是否接受。按仓库规则不直接改写他人票的结论。

**2026-10-24T04:36:53Z**

负责人转交：原负责人为 Frank Qi。2026-10-24 经原负责人确认，转交给 hanjiang。原因：机械校验落在 Research Mapping 与 LLM-Wiki 的候选创建路径上，这两套领域由 hanjiang 负责。本次不改写 Design 与验收标准。拆分结论仍是 2026-10-21 第五轮裁决：格式、对象引用、依赖环在写入时拒绝；基准是否等于当前正式版本仍留给中央 Agent。检查表缩减是否接受，由已转交的「中央 Agent 候选预审检查项与失败处置」(ai4-5z9e) 负责人裁决。
