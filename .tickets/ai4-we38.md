---
id: ai4-we38
status: open
deps: []
links: [ai4-yyy9, ai4-s12u, ai4-z3z4, ai4-iyyn, ai4-csyj, ai4-c2t7, ai4-ufqu, ai4-ujvn, ai4-xem8, ai4-kpvp, ai4-dhpv]
created: 2026-10-21T21:05:00Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-kpvp
tags: [wayfinder:grilling, agent, task-agent, endpoint]
---
# Task Agent 改由研究员端侧自持

推翻「中央部署 Task Agent」的设计。研究员在自己的电脑上编写和运行 task-agent，中央不再承担 agent 的部署、绑定、审核和拉起 Worker。本票是这次推翻的决策入口，并作为受影响的既有票的改写依据。

## Question

确认端侧自持形态下的四条边界：运行时归谁、消息怎么进来、权限怎么限制、结果怎么回到平台。不实现运行时代码。

## Design

### 推翻的旧设计

旧链路（`docs/data-flow/task-agent-binding.md`）：任务节点创建 → 负责人提交声明式设计 → Project Owner 审核 → 中央 Agent 写入绑定 → Gateway 在中央 `task-agent` 容器内拉起短生命周期 Worker。

旧设计的四个成本，是本轮推翻的理由：

1. 中央 Agent 要「部署」，就必须把研究员提交的设计落成可执行形态，等于开出一条执行研究员代码的通道，与「中央 Agent 不执行研究员提交的代码」正面冲突。
2. 需要绑定表、注册表、pending 生效态、部署与启动的区分，而 `registery` 至今没有字段契约。
3. 研究员无法自己调试自己的 agent，改一行要等审核和部署。
4. 中央要维护 task-agent 集群，且每个 agent 的模型与凭据都堆在中央。

### 新形态

研究员在自己的电脑上写 task-agent（fast-agent 卡片或 Python 模块都行），自己启动、自己重启、自己改。中央服务器上没有 task-agent 服务，也没有 agent 注册后部署这一步。

四条边界：

| 边界 | 结论 |
| --- | --- |
| 运行时归属 | 研究员自持。平台不安装、不部署、不重启研究员的 agent |
| 上游消息 | 研究员的 agent 主动连接中央消息队列，订阅自己负责的 TaskNode。出站连接即可，端侧不需要公网可达地址 |
| 权限范围 | 中央服务只部分开放给研究员的 agent，按能力面切分，不按主体逐条授权。见下节 |
| 结果回平台 | agent 把结果作为草稿提交到中央草稿箱对应领域的命名空间；下游交接由领域正式版本发布触发 |

### 中央服务对端侧的开放面

按能力面切分，而不是给每个主体配一份权限清单：

| 调用方 | 能做什么 | 不能做什么 |
| --- | --- | --- |
| 端侧 task-agent | 读写草稿箱，只能检索到自己提交的内容 | 不得读他人草稿；不得写正式存储；不得调管理 MCP 的审核、正式化、推进工具 |
| 研究员（作为人） | 提交 candidate | 不得直接改正式版本；不得接管他人的 TaskNode |
| Project Owner | 全部中央服务 | — |

一个研究员只能访问自己负责的任务的 task-agent。这条是边界，不是可配置项。

### 注册只是记录

研究员部署完自己的 task-agent 后写一条注册记录。这条记录是**事实留痕**，不是代码级约束：它不阻断调用，也不参与鉴权决定。真正的边界由上一节的能力面切分承担。

这样做的理由是：agent 在研究员自己的机器上，平台无法强制它做什么；把注册表当成权限系统会给人错误的强制性印象。它是「谁在跑什么 agent」的可查账本。

### 下游交接的触发点

原设计把交接挂在执行状态机上：执行完成 → 节点负责人接纳 → 发交接消息。端侧自持后中央看不到执行状态机，因此交接改挂在领域正式化上：草稿 → 一审 → 候选 → Project Owner 批准 → 正式版本发布 → 触发下游交接。正式版本本来就有不可变版本号和审计链，触发点比执行状态机更可靠。

## Acceptance Criteria

- [ ] 明确端侧 task-agent 的运行时归属，以及平台不做的事（不安装、不部署、不重启、不托管凭据）
- [ ] 明确上游交接消息的送达方式：端侧主动连接中央队列并订阅所属 TaskNode
- [ ] 明确中央服务对端侧按能力面开放的三档边界，以及「一个研究员只能访问自己负责任务的 agent」这条边界
- [ ] 明确注册记录是事实留痕而非代码约束
- [ ] 明确执行结果的回平台路径与下游交接的触发点
- [ ] 明确 task-agent 与 centre-agent 都是消息驱动：MCP 只承担返修与人工作业，不承担任务下发
- [ ] 受影响的既有票已标注改写或关闭，并写明新的依据

## Notes

**2026-10-21T21:05:00Z**

决策来源：2026-10-21 与 Project Owner 的讨论。原话要点：「不要什么 agent 设计 buffer 了，分配任务后，研究员需要在自己的电脑上写 task-agent，提交一个设计稿留痕就行」「我们只要限制这些 agent 的 mcp 能力就行」「不要在中央搞一个 task-agents 集群，也不要 agent 审核这一套操作」。

讨论中确认：

- 上游消息由研究员的 agent 主动连中央队列（不做端侧入站可达）。
- 注册只是记录，不作为代码约束。
- 结果提交到中央草稿箱（`buffer`），走既有的一审到正式化链路。

受影响票见 `links`。其中 `ai4-s12u` 整条立意消失；`ai4-z3z4`、`ai4-iyyn`、`ai4-csyj`、`ai4-c2t7` 需按端侧自持改写。

**2026-10-21T22:10:00Z**

修正与补充（同日第二轮讨论）：

- 原「按主体注册可用 MCP 能力」改为「中央服务按能力面部分开放给端侧」，不再为每个主体配权限清单。三档边界见正文。
- 明确注册记录只是事实留痕，不是鉴权依据。
- 删去 `sci-weave/centre-control/task-agents/` 空目录：它的位置暗示「部署在中央」，与端侧自持矛盾。task-agent 源码留在 `sci-weave/task-agent/`。
- 新增约束：task-agent 与 centre-agent 都是消息驱动，MCP 只承担返修与人工作业，不承担任务下发。这条推翻了若干已关闭票中的 Owner 命令语义，见「Agent 以消息驱动，MCP 只负责返修」。

**2026-10-22T13:07:00Z**

2026-10-22 修订，依据 ADR-0002。推翻同日「task-agent 源码留在 sci-weave/task-agent/」。

Centre Agent 的源码迁到 sci-weave/centre-control/centre-agents，现有 sci-weave/task-agent 只作为 git mv 的起点，两处落地后删除。Task Agent 不在中央运行，发给研究员的是 deploy-task-agent 套件。删去 centre-control/task-agents 空目录这条仍然成立。
