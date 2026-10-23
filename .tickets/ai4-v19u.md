---
id: ai4-v19u
status: open
deps: []
links: [ai4-yyy9, ai4-xup8, ai4-ufqu, ai4-353s]
created: 2026-10-18T15:18:52Z
type: epic
priority: 1
assignee: hanjiang
parent: ai4-xup8
tags: [wayfinder:grilling]
---
# Agent 套件接入与协作边界分支

厘清 Agent 套件（MCP、Skills、Hooks/extensions）在 SciWeave 中的职责、接入方式和协作边界。按用户要求先建立讨论入口，后续再逐步收敛；本工单不预设技术方案。

## Acceptance Criteria

形成可供后续规划使用的套件边界与职责规格，至少明确平台提供能力与用户自带能力的分工、与端侧 Agent/消息协作及治理流程的接口边界；具体实现和依赖选型另行决策。

## Notes

**2026-10-18T15:39:58Z**

本分支规划变更已推送至 feature/qiyueran，当前提交 622cae7；关联 Pull Request：docs(wayfinder): expand collaboration specification map（https://gitee.com/qi-yueran/ai4science/pulls/8，目标 develop）。本工单保持开放，讨论问题尚未解决。

**2026-10-23 认领与规格收敛（hanjiang）**

身份核对：本票此前无 assignee，现按「未认领工单可由任何身份认领」规则由 hanjiang 认领；当前分支 `feature/hanjiang`、`git config user.name=hanjiang` 一致。本票为地图 `ai4-xup8` 的子分支，其「套件接入边界」由 `ai4-ufqu` 关闭时迁移至此。

收敛成果已写入 `docs/superpowers/specs/2026-10-23-agent-suite-boundary-design.md`，要点：

1. **两类 MCP 分工**：Agent Gateway 的 MCP（人用：返修、处置、回答提问、观察）与平台领域 MCP（Agent 用：读正式数据、写草稿、提交候选）职责不混用；「MCP 只做返修」只约束前者。
2. **运行时套件装载边界**：每次 loop 由短生命周期 Worker 承担，按 TaskNode 模板生成最小权限 Agent profile；Skills 只认显式清单、默认不自动发现也不开 shell；Hooks 只用于 Worker 进程内受控行为，不把个人 Codex Hook 当服务器端 Hook。
3. **平台提供 vs 用户自带**：可复用的能力进平台套件（Work Agent 部署套件、领域 MCP、队列订阅语义、预审判据技能）；研究者本机的 harness、私人 Skills、凭据留在用户侧，平台不读取不托管。
4. **与消息协作及治理的接口**：任务下发只走消息队列；订阅是出站连接；留痕与审计不受套件影响。

范围外维持 `ai4-jfvy` 的结论：Agent Kit manifest、Skills/Hooks 模板体系、ZIP 交付与多套件市场不属本阶段。本票验收标准「形成供后续规划使用的套件边界与职责规格」已具备交付物；是否关闭等待地图负责人确认子分支收敛状态。
