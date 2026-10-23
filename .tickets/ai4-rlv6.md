---
id: ai4-rlv6
status: open
deps: [ai4-he04, ai4-5z9e, ai4-oebi, ai4-oz3s, ai4-8dgd, ai4-a2ba, ai4-t2wc]
links: [ai4-upsm]
created: 2026-10-21T12:16:16Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-fv1r
tags: [centre-control, centre-agents, interface]
---
# 中央 Agent 能力接口收口

在各项能力定稿后，收口中央 Agent 的对外接口形态：进程常驻形态、工具命名与分组、鉴权、以及它调用 Buffer、两套管理 MCP、留痕工具的方式。

## Design

运行时方向见 docs/data-flow/centre-agent.md：fast-agent-mcp 单实例常驻，能力用 MCP 工具区分而非多实例。Gateway 的 MCP 面只承担返修与处置，不承担任务下发。

本票晚于各能力票，因为它要收口的是已经定下来的能力，不是预先猜测的接口。

> 修订（2026-10-21）：原「复用 task-agent 的 Gateway 骨架与租约、审计写法」作废。task-agent 的 Gateway 已随任务负责人部署，与中央 Agent 分属不同部署单元，不再共用代码；中央 Agent 如需进程骨架，自建。

## 首版能力规格（仅定义，不实现）

中央 Agent 以一个常驻 Agent 套件提供以下能力。每项能力最终对应独立、可审计的工具；Mapping 与 Wiki 的工具保持领域隔离。

### 读取能力

- `read_mapping_formal`：读取 Research Mapping 正式内容。
- `read_wiki_formal`：读取 LLM-Wiki 正式内容。
- `list_mapping_candidates`、`read_mapping_candidate`：读取全部 Mapping 候选及其固定 head、正式基准、来源与状态。
- `list_wiki_candidates`、`read_wiki_candidate`：读取全部 Wiki 候选及其固定 head、正式基准、来源与状态。
- `read_agent_registry`：读取主体与 Agent 登记事实，包括中央 Agent 和 Project Owner 的通知联系方式；注册表不参与鉴权。

中央 Agent 读取候选时不受端侧“只能看到自己提交内容”的限制。候选正文由对应领域管理 MCP 提供，中央 Agent 不直连 SQLite、TerminusDB 或其他领域存储。

### 预审与候选写入能力

- `append_mapping_prereview_log`、`append_wiki_prereview_log`：分别向对应领域治理记录追加预审报告；两个工具独立授权。
- `create_mapping_merged_candidate`、`create_wiki_merged_candidate`：分别创建新的混合候选，并记录全部来源候选和来源作者；不修改已有候选，混合候选创建后不授予来源作者操作权。

中央 Agent 不写正式版本、不执行 Owner 正式化、不改变已有候选、不写草稿箱接纳状态、不发起任务、不下发任务，也没有私有审计写入通道。

### PO 通知能力

- `enqueue_project_owner_notification`：根据注册表中的 PO 联系方式创建结构化通知请求。
- 邮件是通知投递方式，不是审核或正式化接口；邮件回复不构成 PO 决定。
- 邮件投递由独立通知组件完成，SMTP 地址、账号和令牌由该组件通过环境变量提供，中央 Agent 不持有邮件凭据。
- 通知失败只记录投递失败并支持重试，不撤销预审报告或候选创建结果。

首版不实现上述工具；本票先收口名称、职责、输入输出边界和禁止能力。详细面向实现者的说明见 `sci-weave/centre-control/centre-agents/README.md`。

## Acceptance Criteria

- 工具清单与各能力票一一对应，无重复无遗漏
- 鉴权与调用者标识有明确来源
- 明确中央 Agent 没有任何写审计的私有通道
- 明确 Gateway 的 MCP 面只承担返修与处置，不承担任务下发；任务由消息驱动


## Notes

**2026-10-21T12:48:25Z**

2026-10-21 修订：中央 Agent 职责收窄后，本票只需收口两条线——部署 Task Agent，以及候选版本预审与合并。调度、失败处置、消息队列入口、正式版本推进均不在范围内，对应票已关闭。

> 更正（2026-10-21T22:42:00Z）：「部署 Task Agent」这条线已随端侧自持取消，本票只剩**一条**收口线——候选版本预审与合并。相应依赖 `ai4-s12u` 已在同日关闭。

**2026-10-21T13:18:41Z**

2026-10-21T21:20:00Z

边界变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)。本票 Design 中「复用 task-agent 的 Gateway 骨架与租约、审计写法」这一条作废：

- Task Agent 的 Gateway 移到研究员自己的电脑上，与中央 Agent 分属不同部署单元、不同项目组，不再共用代码。
- 中央 Agent 如需进程骨架与审计写法，自建即可，不再引用端侧实现。
- 中央 Agent 只对外暴露管理 MCP，不暴露 Owner 命令类工具，也不承担消息队列消费。

仍然成立的收口项：工具清单与各能力票对应、鉴权与调用者标识来源、没有写审计的私有通道。另新增一项：按主体登记 MCP 能力的校验由「端侧 Agent 的 MCP 能力注册与限制」(ai4-ujvn) 定义，本票需说明中央 Agent 自身的工具是否参与该校验。

**2026-10-21T14:36:24Z**

2026-10-21T22:42:30Z

依赖调整：解除对「中央 Agent 按已批准绑定部署 Task Agent」(ai4-s12u) 的阻塞依赖。该票已于 2026-10-21 关闭，且其立意（中央部署 Task Agent）已随端侧自持取消。本票其余依赖不变。

**2026-10-21T23:45:00Z**

2026-10-21 第五轮讨论的修订。本票挂到「中央 Agent 候选预审职能地图」(ai4-fv1r) 之下，收口范围与新增依赖：

- 依赖增加「候选方案合成与送审」(ai4-oebi)，因为混合候选是它唯一要收口的写操作。
- 工具清单需要按工具粒度收口：`append_prereview_log` 与 `create_merged_candidate` 是两个独立工具，权限可分开配置。见「预审报告的追加日志契约」(ai4-oz3s) 与「注册表登记中央 Agent 与开放面第四档」(ai4-t2wc)。
- 「中央 Agent 自身的工具是否参与注册表校验」已有答案：进注册表但只留痕，不参与鉴权；开放面按工具面收口，不按登记记录授权。
- 中央 Agent 只保留预审一类职能，不新增其他能力。这条本身就是本票的收口原则。
