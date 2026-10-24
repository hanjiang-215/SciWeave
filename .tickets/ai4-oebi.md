---
id: ai4-oebi
status: closed
deps: [ai4-5z9e]
links: [ai4-5z9e, ai4-8dgd]
created: 2026-10-21T12:14:51Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-fv1r
tags: [centre-control, centre-agents, proposal]
---
# 候选方案合成与送审

中央 Agent 针对同一正式基准上的有效候选，生成一个或多个完整方案（采用单个、混合、建议放弃），并把完整来源、Diff、影响范围和判断依据交给 Project Owner 选择。

## Design

依据「正式版本前进后候选重放与冲突审核规则」：可兼容组合由中央 Agent 提出，任何修改都生成新的不可变候选版本，Project Owner 批准的是确切版本；中央 Agent 不替 Project Owner 做最终选择。

待定项已全部定案（2026-10-24，见本票 Resolution）：

- 混合方案的生成方式；
- 方案数量上限；
- 送审的调用形态。

## Resolution

### 生成方式（2026-10-24 定案）

**规则驱动，不依赖模型。** 首版混合候选只按可机械判定的规则合成，中央 Agent 不调用生成式模型：

- 合成对象：同一 `base_formal_revision_id` 上、`preview` 通过且无 `conflict`/`stale` 障碍的可送审候选；合并到同一混合候选前，各来源候选的 `candidate_head` 必须固定（差分基于精确 Commit，不基于 branch 最新）。
- 兼容性判定：以合成后的对象级语义与约束为准，不以节点/字段是否同名作为唯一依据（沿用 `ai4-iciy` Resolution）。合成结果经领域机械校验通过后才是候选（复用 `ai4-eex0` 已前移的机械校验）。
- **语义依据不足不得合成**：无法说明影响范围或无法判断兼容的组合，中央 Agent 生成报告的 "not_synthesizable" 事实并交 PO 处理，不把未经确认的组合标记为已验证兼容。判断不了就说判断不了（沿用 `ai4-8dgd`）。
- 合成由 `create_merged_candidate` 承载，作者记为全部来源作者且来源作者无操作权、不可二次混合（沿用 `ai4-8dgd`），不引入新的 Proposal 状态。

### 方案数量上限（2026-10-24 定案）

**一次预审、同一基准，至多送审 3 个混合候选方案。** 可合成组合按影响范围由小到大排序，取前 3；超出部分只在预审报告里列出"存在更多可合成组合"，由 PO 在送审通知里要求中央 Agent 对特定来源组合再合成。理由：方案数量失控会让 PO 选择面过大且送审载荷不可控；上限只在一次送审内生效，不影响后续按 PO 指定范围继续合成。

### 送审的调用形态（2026-10-24 定案）

送审 = **写混合候选 + 入队 PO 通知**，两件事独立且顺序固定：

1. 混合候选经 `create_mapping_merged_candidate` / `create_wiki_merged_candidate` 写入领域治理记录（只新建、不改写已有候选）。
2. 随后调用 `enqueue_project_owner_notification` 建结构化通知请求，载荷引用候选、预审报告、冲突与混合候选的**稳定标识**，不携带候选正文；PO 经自己的 MCP 查看候选详情并做选择（沿用 `ai4-rlv6` 工具名与 `centre-agents/README.md` 的「通知 PO」节）。

通知投递失败只记录失败并支持重试，不撤销已写入的混合候选（沿用 centre-agents README）。

## Acceptance Criteria

- [x] 方案引用完整来源与基准版本
- [x] 生成的混合结果是新的不可变候选，不改写他人候选
- [x] 语义依据不足的组合不得作为已验证兼容方案呈现
- [x] 中央 Agent 无法替 Project Owner 选择
- [x] 一次预审同一基准送审方案数量有上限（3），超出部分可查明
- [x] 送审路径只有「写候选 + 入队 PO 通知」两步，通知不携带正文

## Notes

**2026-10-21T23:45:00Z**

2026-10-21 第五轮讨论的修订。本票挂到「中央 Agent 候选预审职能地图」(ai4-fv1r) 之下，并收窄为只承载混合候选：

- **混合候选确认保留**，不再是「待定」。生成方式、作者身份、操作权与禁止二次混合的约束见「混合候选的生成与作者身份」(ai4-8dgd)。
- **「采用单个」与「建议放弃」两种方案不属于本票**：建议放弃属于预审结论，「采用单个」是 PO 的选择而不是中央 Agent 的合成产物。本票只剩混合候选的生成与送审。
- **冲突矩阵移出本票**：它与「先看哪个候选」的判断一起并入「中央 Agent 候选预审检查项与失败处置」(ai4-5z9e) 的报告格式。

**2026-10-24T10:08:21Z**

转交说明（2026-10-24）：assignee 由 Frank Qi 改为 hanjiang，依据 Gitee issue https://gitee.com/qi-yueran/ai4science/issues/IKQ63M 的第 1 条请求与本节裁决。原负责人 Frank Qi，转交原因：本票 deps 为 ai4-5z9e（已转 hanjiang），正文已收窄为只承载混合候选，生成方式与作者身份约束见 ai4-8dgd，链路在 hanjiang 手上连贯。

**2026-10-24 待定项定案（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

三个待定项按上述 Resolution 定案：生成方式规则驱动不依赖模型；一次预审同一基准至多送审 3 个混合候选方案；送审 = `create_*_merged_candidate` 写候选 + `enqueue_project_owner_notification` 入队通知（载荷只带稳定标识）。验收六项全部勾选。本票规格侧完成，保持 open 待 `ai4-5z9e` 与写端工具（`create_merged_candidate`，依赖 `ai4-t2wc`/`ai4-rlv6`）收口后落实现与回归测试。
