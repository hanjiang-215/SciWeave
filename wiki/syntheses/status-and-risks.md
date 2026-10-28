---
type: synthesis
created: 2026-10-28
updated: 2026-10-28
sources: [repository-facts]
tags: [status, risks, implementation, contradictions]
---

# 实现状态与风险

## 当前结论

SciWeave 的主要领域服务、治理 MCP、中央草稿箱、Coordinator、Registry、通知、Dashboard 和两类 Agent 套件已经形成可运行的工程骨架，并有大量单元/集成测试与部署验证记录。完整生产闭环仍需把“代码存在”“测试通过”“中央容器已部署”“SciencePal 实际执行”和“公网可访问”区分开看。

## 已有证据

| 范围 | 当前证据 |
|---|---|
| Research Mapping | 领域服务、候选/正式化流程、TerminusDB 集成与测试；项目总结记录 132 项相关测试口径 |
| LLM-Wiki | 文档/资源资格、候选与正式化流程、TerminusDB 集成与测试；项目总结记录 141 项测试口径 |
| Draft Buffer | 服务、MCP、幂等、固定 Commit 和 TerminusDB 测试 |
| Agent runtime | 研究员 runtime、MCP 注入、多 Agent workflow 和部署配置测试 |
| Dashboard | Dashboard API 聚合、来源降级和 Vue 页面测试/构建 |
| 中央部署 | centre-stack 单容器、多进程、启动/健康检查/播种验证记录 |
| 演示证据 | Iris 数据输入、KNN 基线、平台治理链路与 SciencePal bridge 证据记录 |

## 仍需注意

- SciencePal 实际承载执行和公开评审链接依赖外部平台与网络条件；本地脚本复现不等于真实平台演练。
- 公网反向代理、TLS 和生产密钥管理尚未由仓库确定。
- Redpanda 生产高可用、保留期、跨机器 advertised listener 尚未确定。
- `gateway/ingest` 的 README、实际源码/测试和 centre-stack 进程清单对事件消费闭环的描述不一致，需要后续明确是否纳入中央部署及启动方式。
- `shared/message-envelope` 尚无生产调用方，不能据目标 schema 推断当前线上消息已经统一。
- 空库或未配置 subscriber/SMTP 时，看板来源可能为 `unavailable`，这属于状态降级，不必然表示 Dashboard API 故障。
- 中央容器实测曾出现 subscriber 因缺少模型 Key 而 FATAL；这是无模型配置时的设计行为，不应伪装成真实执行成功。

## 维护建议

1. 先核实 ingest 的真实部署边界和端到端测试，再更新本 Wiki 的实现状态。
2. 消息信封迁移完成后，补充生产调用方、版本策略和兼容验证证据。
3. 每次部署形态、外部服务或测试口径变更时，更新来源页和本页。
4. 对外发布前补齐 TLS、反代、凭据注入和 Linux 容器验证。

## 相关页面

- [[entities/sciweave]]
- [[concepts/core-flow]]
- [[concepts/deployment-and-operations]]
- [[sources/repository-facts]]

## Contradictions

详见 [[sources/repository-facts#contradictions]]。本页面保留风险结论，不删除原始来源中的相互矛盾表述。
