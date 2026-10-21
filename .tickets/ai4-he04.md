---
id: ai4-he04
status: open
deps: [ai4-upsm]
links: [ai4-upsm, ai4-5z9e]
created: 2026-10-21T12:14:32Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, centre-agents, candidate-prereview]
---
# 中央 Agent 候选预审入口与结论回写

中央 Agent 从 Research Mapping 与 LLM-Wiki 的管理 MCP 读取**已存在的候选分支**，生成预审材料，并把结论写回该候选的治理记录。草稿箱不参与这条链路。

## Design

修订（2026-10-21）：本票原为「Buffer 取件与预审结论回写」，假设中央 Agent 读草稿箱里已接纳的提交。讨论结论是草稿一审由人完成、通过后由人调用领域管理 MCP 写入候选分支，中央 Agent 的工作从候选存在那一刻开始，因此入口从草稿箱改为领域管理 MCP 的候选读取。原表述见下方 Notes 的修订记录。

已定边界：

- 中央 Agent 对中央草稿箱只读或不读，绝不写草稿的 `accepted`/`rejected`。
- 一审由命名空间配置的审核人完成；转成候选由人调用领域管理 MCP 完成，不是中央 Agent 代劳。
- 中央 Agent 只处理候选：读取精确 candidate head、base formal revision 与候选内容，产出预审材料并回写结论。
- 结论写回领域治理记录（不是草稿箱），并经留痕工具追加审计。

待定：

- 预审入口形态：由领域管理 MCP 新增只读候选查询工具，还是中央 Agent 直接用现有 Store 接口。
- 取件是否带租约以避免两个中央 Agent 实例重复预审同一候选。
- 预审结论的状态取值与它和 Proposal 状态（`candidate`、`mr_ready`、`stale`、`conflict`）的对应关系。
- 中央 Agent 能否为「需要混合」的候选写新候选分支；若可以，它的写入位置与作者身份如何记录。

## Acceptance Criteria

- 只能读到已存在的候选分支；草稿箱内容不进入预审输入
- 不写草稿的接纳或驳回状态
- 同一候选 head 不会被并发预审两次，或被重复预审时结论一致
- 预审结论写回领域治理记录并留痕，不写正式版本
- 候选 head 或 base formal revision 变化后，旧预审结论失效且有明确标记
- 有回归测试覆盖重复取件、并发取件与预审对象变化

## Notes

**2026-10-21 修订记录**

原题「Buffer 取件与预审结论回写」，原 Design 为「中央 Agent 从 Buffer 取出『领域审核人已接纳』的提交」。该前提已被 2026-10-21 讨论推翻：草稿的一审是人，转候选是人调用 MCP，中央 Agent 审的是候选。冲突记录见 `docs/data-flow/draft-buffer.md` 第 8 节。
