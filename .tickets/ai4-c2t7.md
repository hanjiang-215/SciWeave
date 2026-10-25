---
id: ai4-c2t7
status: open
deps: [ai4-xup8]
links: []
created: 2026-10-20T06:31:26Z
type: task
priority: 1
assignee: hanjiang
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# Task Agent 初始化所需的 Mapping 查询契约

## Question

当 Mapping 开发完成并提供查询能力后，确定 Task Agent 初始化时读取 TaskNode、Task Owner、必要上游与配置版本所需的最小只读查询契约。该票只定义消费端需要的请求前置条件、响应字段、版本标识、空结果与不可用错误语义；不设计 Mapping 写入、运行期回调或领域 Buffer。

> 修订（2026-10-21）：端侧 agent 被设计为**持有自己的 MCP 客户端、可随时只读查询地图**，因此原文「运行期不依赖 Mapping 查询」不再成立。新的边界：初始化必须查询一次并持久化快照（供订阅与隔离使用）；运行期**允许**只读查询以获取上下文，但必须定义中央 Mapping 不可用时的降级行为。

## Acceptance Criteria

确认由 Mapping 提供的最小只读初始化查询能力及其输入前置条件；明确 Task Agent 必需的 TaskNode、Task Owner、必要上游与配置版本字段；明确空结果、未授权、暂不可用和版本不兼容的错误语义；不引入 Mapping 写入、领域 Buffer 或运行期回调。

> 修订（2026-10-21）：删去原文「仅在显式初始化时查询并持久化快照，运行期不依赖 Mapping 查询」。改为：初始化查询并持久化快照；运行期允许只读查询；须定义只读查询不可用时的降级行为（例如沿用快照继续执行，或阻塞并上报）。

## Notes

**2026-10-25 负责人转交（hanjiang 操作，经 Frank Qi 授权）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据 Gitee issue https://gitee.com/qi-yueran/ai4science/issues/IKQ8BD 第 1 条，Frank Qi 授权 hanjiang 直接转交。转交原因：本票阻塞于 `ai4-xup8`（hanjiang 地图），且契约所需的 `list_candidates`/`list_reviewable_candidates` 只读工具已由 hanjiang 实现，转由 hanjiang 承接最顺。正文与验收标准不改写，仅变更归属并记录。

**2026-10-21T13:10:19Z**

2026-10-21T21:14:00Z

消费端位置变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)：本票定义的初始化只读查询契约仍然成立，但请求方从「中央 Gateway」变为「研究员电脑上的端侧 agent」。

对本票的影响：

- 查询调用方是端侧进程，凭主体身份调用中央 Mapping 管理 MCP，需要经过「端侧 Agent 的 MCP 能力注册与限制」(ai4-ujvn) 的主体校验。
- 「仅在显式初始化时查询并持久化快照」这条仍然成立，快照留在端侧。
- 空结果、未授权、暂不可用、版本不兼容四种错误语义不变。
- 解除对 ai4-xup8 的依赖关系待复盘：本票原本等 Mapping 领域规格收敛，该依赖仍然有效，无需改动。

本票仍 open。

**2026-10-21T14:58:58Z**

2026-10-21T22:58:00Z

推翻上述 2026-10-21T21:14:00Z 的一条：原文说「本票原本等 Mapping 领域规格收敛，该依赖仍然有效」，同时按旧设计写「运行期不依赖 Mapping 查询」。

2026-10-21 第四轮讨论确认：端侧 agent 会有自己的 MCP 客户端，可以查地图；构建 fast-agent 时提示词会告知它负责哪个任务节点。因此运行期只读查询是允许的。

本票据此改写正文与验收标准：

- 初始化必须查询并持久化快照（保留）。
- 运行期允许只读查询（新增）。
- 需要定义只读查询不可用时的降级行为（新增）。
- 身份（负责哪个 TaskNode）由配置项与提示词双重表达，不由提示词单独承载。

依赖 ai4-xup8 保持不变，仍在等 Mapping 领域规格暴露只读查询接口。
