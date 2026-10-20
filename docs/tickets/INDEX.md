# SciWeave 工单索引

> 由 `ticket-index` 技能生成：事实来自 `.tickets/`，归属与简介来自 [`index.toml`](index.toml)；请勿手工编辑。
> 工单变更后运行 `python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py render`。

## 读法

- 找工单：先看模块导航，再打开模块文件；定位到候选后再读 `.tickets/<id>.md` 全文。
- `open` 待开始，`in_progress` 进行中，`closed` 已验收关闭；**活跃**指前两者。
- 带 `map` 标记的是 Wayfinder 地图；层级只来自 `parent`，`links` 表达关联。
- 跨模块工单只在主模块展开；其他模块的归属、依赖和关联见“跨模块关系”。

## 总览

- 工单总数 **66**：open 14 · in_progress 4 · closed 48
- 类型：epic 18 · task 18 · grilling 12 · feature 11 · chore 3 · prototype 2 · research 2
- 地图 4 张 · 活跃 18 张 · 跨模块关系 45 条

## 负责人（活跃工单）

| 负责人 | open | in_progress | 活跃合计 |
| --- | ---: | ---: | ---: |
| Frank Qi | 11 | 2 | 13 |
| hanjiang | 2 | 2 | 4 |
| 未分配 | 1 | 0 | 1 |

## 模块导航

| 模块 | 范围 | 工单 | 活跃 | 地图 |
| --- | --- | ---: | ---: | ---: |
| [产品与需求](modules/product.md) | 平台定位、首版范围、研究图与协作模型、资源共享、演示场景、看板可见性 | 8 | 2 | 1 |
| [Research Mapping](modules/mapping.md) | TaskNode/依赖边模型、草稿与正式视图、提案生命周期、TerminusDB 验证与持久化 | 11 | 1 | 1 |
| [LLM-Wiki](modules/wiki.md) | Wiki 内容与资源引用、Buffer/Proposal 生命周期、候选治理记录、分支能力验证 | 6 | 0 | 0 |
| [提案治理与审计](modules/governance.md) | 统一提案语义、候选并发与重放、跨存储一致性、中央协调与审计 | 6 | 0 | 1 |
| [Agent 与消息协作](modules/agent.md) | 端侧 Agent 角色、消息与交接、套件接入、Task Agent 部署与运行时验证 | 12 | 7 | 0 |
| [Gateway 与执行运行时](modules/gateway.md) | Gateway MVP、Owner MCP、状态与端口、Worker 调度、fast-agent 适配与验收 | 16 | 7 | 1 |
| [工程基础设施](modules/infra.md) | 依赖与工具链、技术栈与目录规范、本地服务与版本固定 | 7 | 1 | 0 |

## 当前前沿

依赖已满足的活跃工单，可直接认领或继续。

| 工单 | 模块 | 负责人 |
| --- | --- | --- |
| [ai4-2sgd](../../.tickets/ai4-2sgd.md) 工单索引自动同步钩子与增量审查 | 工程基础设施 | hanjiang |
| [ai4-353s](../../.tickets/ai4-353s.md) Task Owner 通道（MCP）与上游交接队列物理隔离 | Gateway 与执行运行时 | Frank Qi |
| [ai4-6v70](../../.tickets/ai4-6v70.md) Web 看板与平台状态可见性分支 | 产品与需求 | hanjiang |
| [ai4-a9zd](../../.tickets/ai4-a9zd.md) 验证 fast-agent-mcp 外部进程与 A2A 启动路径 | Agent 与消息协作 | Frank Qi |
| [ai4-aaff](../../.tickets/ai4-aaff.md) SciWeave 默认科研示例场景与验证证据 | 产品与需求 | hanjiang |
| [ai4-csyj](../../.tickets/ai4-csyj.md) TaskNode 交接消息发布与下游触发流程 | Agent 与消息协作 | Frank Qi |
| [ai4-kpvp](../../.tickets/ai4-kpvp.md) 端侧 Agent 协作与治理分支 | Agent 与消息协作 | Frank Qi |
| [ai4-m96w](../../.tickets/ai4-m96w.md) 带 Worker Lease 的本地调度与测试运行时 | Gateway 与执行运行时 | Frank Qi |
| [ai4-te1v](../../.tickets/ai4-te1v.md) 消息队列协作模型分支 | Agent 与消息协作 | Frank Qi |
| [ai4-ufqu](../../.tickets/ai4-ufqu.md) Task Agent 运行时与套件接入方案 | Agent 与消息协作 | Frank Qi |
| [ai4-v19u](../../.tickets/ai4-v19u.md) Agent 套件接入与协作边界分支 | Agent 与消息协作 | 未分配 |
| [ai4-xup8](../../.tickets/ai4-xup8.md) Research Mapping 与 Wiki 领域数据模型和持久化规格地图 | Research Mapping | hanjiang |
| [ai4-yyy9](../../.tickets/ai4-yyy9.md) Gateway 与最小 fast-agent 执行闭环规格地图 | Gateway 与执行运行时 | Frank Qi |
| [ai4-z3z4](../../.tickets/ai4-z3z4.md) 最小 Task Agent 项目组实现规格 | Gateway 与执行运行时 | Frank Qi |

## 阻塞中的活跃工单

| 工单 | 模块 | 阻塞于 |
| --- | --- | --- |
| [ai4-2h8c](../../.tickets/ai4-2h8c.md) fast-agent Runtime Adapter 与固定会话恢复 | Gateway 与执行运行时 | [ai4-m96w](../../.tickets/ai4-m96w.md)（in_progress） |
| [ai4-c2t7](../../.tickets/ai4-c2t7.md) Task Agent 初始化所需的 Mapping 查询契约 | Agent 与消息协作 | [ai4-xup8](../../.tickets/ai4-xup8.md)（open） |
| [ai4-gqj3](../../.tickets/ai4-gqj3.md) ExecutionRecord 控制、审核与恢复 MCP 工具 | Gateway 与执行运行时 | [ai4-m96w](../../.tickets/ai4-m96w.md)（in_progress） |
| [ai4-iyyn](../../.tickets/ai4-iyyn.md) 最小 Task Agent 项目组端到端验收 | Gateway 与执行运行时 | [ai4-gqj3](../../.tickets/ai4-gqj3.md)（open）、[ai4-2h8c](../../.tickets/ai4-2h8c.md)（open） |

## 待补负责人

活跃但 `assignee` 为空或仍是团队占位名的工单，需要指定具体个人。

| 工单 | 状态 | 当前 assignee |
| --- | --- | --- |
| [ai4-v19u](../../.tickets/ai4-v19u.md) Agent 套件接入与协作边界分支 | open | `空` |

## 跨模块关系

### 多模块归属

| 工单 | 主模块 | 同时归属 |
| --- | --- | --- |
| [ai4-353s](../../.tickets/ai4-353s.md) Task Owner 通道（MCP）与上游交接队列物理隔离 | Gateway 与执行运行时 | Agent 与消息协作 |
| [ai4-c2t7](../../.tickets/ai4-c2t7.md) Task Agent 初始化所需的 Mapping 查询契约 | Agent 与消息协作 | Research Mapping |
| [ai4-m0vt](../../.tickets/ai4-m0vt.md) 首版任务执行、交接与失败恢复模型 | Research Mapping | Agent 与消息协作 |
| [ai4-x3nx](../../.tickets/ai4-x3nx.md) Research Mapping 与 Wiki 候选变更并发治理地图 | 提案治理与审计 | Research Mapping、LLM-Wiki |
| [ai4-xup8](../../.tickets/ai4-xup8.md) Research Mapping 与 Wiki 领域数据模型和持久化规格地图 | Research Mapping | LLM-Wiki、Agent 与消息协作 |
| [ai4-yyy9](../../.tickets/ai4-yyy9.md) Gateway 与最小 fast-agent 执行闭环规格地图 | Gateway 与执行运行时 | Agent 与消息协作 |

### 依赖与关联

只列跨模块的边；同一对工单的对称关联只出现一次。

| 工单 | 关系 | 对方工单 | 涉及模块 |
| --- | --- | --- | --- |
| [ai4-2sdn](../../.tickets/ai4-2sdn.md) | 依赖 | [ai4-9hcj](../../.tickets/ai4-9hcj.md) | LLM-Wiki、Research Mapping |
| [ai4-353s](../../.tickets/ai4-353s.md) | 关联 | [ai4-ufqu](../../.tickets/ai4-ufqu.md) | Agent 与消息协作、Gateway 与执行运行时 |
| [ai4-353s](../../.tickets/ai4-353s.md) | 关联 | [ai4-v19u](../../.tickets/ai4-v19u.md) | Agent 与消息协作、Gateway 与执行运行时 |
| [ai4-353s](../../.tickets/ai4-353s.md) | 关联 | [ai4-xup8](../../.tickets/ai4-xup8.md) | Gateway 与执行运行时、Research Mapping |
| [ai4-3nru](../../.tickets/ai4-3nru.md) | 依赖 | [ai4-36ek](../../.tickets/ai4-36ek.md) | LLM-Wiki、提案治理与审计 |
| [ai4-3nru](../../.tickets/ai4-3nru.md) | 依赖 | [ai4-u3rs](../../.tickets/ai4-u3rs.md) | Research Mapping、提案治理与审计 |
| [ai4-3nru](../../.tickets/ai4-3nru.md) | 依赖 | [ai4-zewm](../../.tickets/ai4-zewm.md) | LLM-Wiki、提案治理与审计 |
| [ai4-5j2j](../../.tickets/ai4-5j2j.md) | 依赖 | [ai4-9hcj](../../.tickets/ai4-9hcj.md) | Research Mapping、工程基础设施 |
| [ai4-aaff](../../.tickets/ai4-aaff.md) | 依赖 | [ai4-m0vt](../../.tickets/ai4-m0vt.md) | Research Mapping、产品与需求 |
| [ai4-aaff](../../.tickets/ai4-aaff.md) | 依赖 | [ai4-r3so](../../.tickets/ai4-r3so.md) | Research Mapping、产品与需求 |
| [ai4-aaff](../../.tickets/ai4-aaff.md) | 依赖 | [ai4-vbnr](../../.tickets/ai4-vbnr.md) | 产品与需求、提案治理与审计 |
| [ai4-aaff](../../.tickets/ai4-aaff.md) | 依赖 | [ai4-xrxw](../../.tickets/ai4-xrxw.md) | Research Mapping、产品与需求 |
| [ai4-ay0e](../../.tickets/ai4-ay0e.md) | 依赖 | [ai4-dy2x](../../.tickets/ai4-dy2x.md) | 产品与需求、提案治理与审计 |
| [ai4-ay0e](../../.tickets/ai4-ay0e.md) | 依赖 | [ai4-vbnr](../../.tickets/ai4-vbnr.md) | 产品与需求、提案治理与审计 |
| [ai4-azx2](../../.tickets/ai4-azx2.md) | 依赖 | [ai4-56iu](../../.tickets/ai4-56iu.md) | LLM-Wiki、提案治理与审计 |
| [ai4-azx2](../../.tickets/ai4-azx2.md) | 依赖 | [ai4-yl2o](../../.tickets/ai4-yl2o.md) | Research Mapping、提案治理与审计 |
| [ai4-c2t7](../../.tickets/ai4-c2t7.md) | 依赖 | [ai4-xup8](../../.tickets/ai4-xup8.md) | Agent 与消息协作、Research Mapping |
| [ai4-dy2x](../../.tickets/ai4-dy2x.md) | 依赖 | [ai4-9f7i](../../.tickets/ai4-9f7i.md) | 产品与需求、提案治理与审计 |
| [ai4-dy2x](../../.tickets/ai4-dy2x.md) | 依赖 | [ai4-e257](../../.tickets/ai4-e257.md) | 产品与需求、提案治理与审计 |
| [ai4-dy2x](../../.tickets/ai4-dy2x.md) | 依赖 | [ai4-ebqx](../../.tickets/ai4-ebqx.md) | 产品与需求、提案治理与审计 |
| [ai4-dy2x](../../.tickets/ai4-dy2x.md) | 依赖 | [ai4-saug](../../.tickets/ai4-saug.md) | 产品与需求、提案治理与审计 |
| [ai4-dy2x](../../.tickets/ai4-dy2x.md) | 关联 | [ai4-xrxw](../../.tickets/ai4-xrxw.md) | Research Mapping、提案治理与审计 |
| [ai4-e257](../../.tickets/ai4-e257.md) | 关联 | [ai4-m0vt](../../.tickets/ai4-m0vt.md) | Research Mapping、产品与需求 |
| [ai4-hkdz](../../.tickets/ai4-hkdz.md) | 依赖 | [ai4-3nru](../../.tickets/ai4-3nru.md) | LLM-Wiki、提案治理与审计 |
| [ai4-iciy](../../.tickets/ai4-iciy.md) | 关联 | [ai4-xup8](../../.tickets/ai4-xup8.md) | Research Mapping、提案治理与审计 |
| [ai4-m0vt](../../.tickets/ai4-m0vt.md) | 依赖 | [ai4-ay0e](../../.tickets/ai4-ay0e.md) | Research Mapping、产品与需求 |
| [ai4-m0vt](../../.tickets/ai4-m0vt.md) | 关联 | [ai4-vbnr](../../.tickets/ai4-vbnr.md) | Research Mapping、提案治理与审计 |
| [ai4-m0vt](../../.tickets/ai4-m0vt.md) | 关联 | [ai4-yvh2](../../.tickets/ai4-yvh2.md) | Gateway 与执行运行时、Research Mapping |
| [ai4-mjku](../../.tickets/ai4-mjku.md) | 依赖 | [ai4-3nru](../../.tickets/ai4-3nru.md) | Research Mapping、提案治理与审计 |
| [ai4-r3so](../../.tickets/ai4-r3so.md) | 依赖 | [ai4-ebqx](../../.tickets/ai4-ebqx.md) | Research Mapping、产品与需求 |
| [ai4-ru15](../../.tickets/ai4-ru15.md) | 关联 | [ai4-x3nx](../../.tickets/ai4-x3nx.md) | 产品与需求、提案治理与审计 |
| [ai4-saug](../../.tickets/ai4-saug.md) | 关联 | [ai4-xup8](../../.tickets/ai4-xup8.md) | Research Mapping、产品与需求 |
| [ai4-u3rs](../../.tickets/ai4-u3rs.md) | 依赖 | [ai4-e257](../../.tickets/ai4-e257.md) | Research Mapping、产品与需求 |
| [ai4-u3rs](../../.tickets/ai4-u3rs.md) | 依赖 | [ai4-ebqx](../../.tickets/ai4-ebqx.md) | Research Mapping、产品与需求 |
| [ai4-ufqu](../../.tickets/ai4-ufqu.md) | 关联 | [ai4-xup8](../../.tickets/ai4-xup8.md) | Agent 与消息协作、Research Mapping |
| [ai4-ufqu](../../.tickets/ai4-ufqu.md) | 关联 | [ai4-yyy9](../../.tickets/ai4-yyy9.md) | Agent 与消息协作、Gateway 与执行运行时 |
| [ai4-v19u](../../.tickets/ai4-v19u.md) | 关联 | [ai4-xup8](../../.tickets/ai4-xup8.md) | Agent 与消息协作、Research Mapping |
| [ai4-v19u](../../.tickets/ai4-v19u.md) | 关联 | [ai4-yyy9](../../.tickets/ai4-yyy9.md) | Agent 与消息协作、Gateway 与执行运行时 |
| [ai4-vbnr](../../.tickets/ai4-vbnr.md) | 依赖 | [ai4-9f7i](../../.tickets/ai4-9f7i.md) | 产品与需求、提案治理与审计 |
| [ai4-vbnr](../../.tickets/ai4-vbnr.md) | 依赖 | [ai4-e257](../../.tickets/ai4-e257.md) | 产品与需求、提案治理与审计 |
| [ai4-vbnr](../../.tickets/ai4-vbnr.md) | 依赖 | [ai4-ebqx](../../.tickets/ai4-ebqx.md) | 产品与需求、提案治理与审计 |
| [ai4-wd5l](../../.tickets/ai4-wd5l.md) | 关联 | [ai4-yvh2](../../.tickets/ai4-yvh2.md) | Agent 与消息协作、Gateway 与执行运行时 |
| [ai4-x3nx](../../.tickets/ai4-x3nx.md) | 关联 | [ai4-xup8](../../.tickets/ai4-xup8.md) | Research Mapping、提案治理与审计 |
| [ai4-xrxw](../../.tickets/ai4-xrxw.md) | 依赖 | [ai4-ay0e](../../.tickets/ai4-ay0e.md) | Research Mapping、产品与需求 |
| [ai4-xup8](../../.tickets/ai4-xup8.md) | 关联 | [ai4-yyy9](../../.tickets/ai4-yyy9.md) | Gateway 与执行运行时、Research Mapping |

## 维护约定

- 事实来源：`.tickets/ai4-*.md` 的 frontmatter，通过 `fer` 修改；索引不缓存可推导事实。
- 归属与简介：`docs/tickets/index.toml`，由人维护；脚本不推断一句话简介。
- 生成：`python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py render`。
- 校验：`python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py check`，退出码 0 才算一致。
- 模块 = 工单结论落地的领域；一张票只在一个模块展开，跨模块关系单独汇总。
- 本文件与 `modules/*.md` 都是生成物；手改会在下一次 `check` 中报过期。
