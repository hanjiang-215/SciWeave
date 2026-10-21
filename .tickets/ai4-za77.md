---
id: ai4-za77
status: open
deps: []
links: [ai4-we38, ai4-ujvn, ai4-v19u]
created: 2026-10-21T22:43:00Z
type: feature
priority: 1
assignee: Frank Qi
tags: [toolkit, task-agent, researcher]
---
# 建立新 Task Agent 的套件

研究员要能在自己的电脑上建出一个新的 task-agent。本票定义这份套件的内容与形态：装什么、怎么装、装完能做什么。目录 `sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/` 已建但为空。

## Problem Statement

端侧自持之后，「新增一个 task-agent」是研究员自己的事。目前平台没有提供任何东西帮他做：没有模板、没有初始化脚本、没有说明应该把 Gateway 放在哪、怎么连中央队列、怎么调中央的领域 MCP。

`ai4-we38` 定了形态（研究员自持、主动连队列、结果交草稿箱），`ai4-ujvn` 定了中央服务的开放面，但没有任何票把这两条落成研究员上手就能用的东西。

## Solution

`researcher-agent-toolkit/deploy-task-agent` 是一份可打包发给研究员的套件，包含三部分：模板、初始化脚本、使用说明。

## Design

### 套件内容

| 组成 | 内容 |
| --- | --- |
| Gateway 模板 | 一份可运行的 Gateway：MCP 入口、消息订阅器、共享 SQLite、短生命周期 Worker、原子 Worker 租约 |
| Agent 定义模板 | fast-agent 卡片模板，含任务指令、允许的模型、允许引用的领域 MCP |
| 初始化脚本 | 复制模板到指定目录、生成 `.env.example`、初始化 SQLite schema、打印下一步 |
| 使用说明 | 怎么填 `.env`、怎么启动、怎么验证、怎么重启、怎么查看执行记录 |

### 与已有实现的关系

`sci-weave/task-agent/` 已有可运行的 Gateway 与 Worker（约 1550 行）。本套件以它为模板基线，不是另写一套。差异在于：模板需要参数化任务节点、队列地址与领域 MCP 引用，而现有实现把这些写死在配置里。

### 套件不做的事

- 不负责部署：研究员自己复制、自己起进程。
- 不托管凭据：`.env` 由研究员自己填，套件只提供 `.env.example`。
- 不包含中央侧的任何东西：中央队列、领域 MCP 都不在套件里，套件只提供客户端配置方式。
- 不做 agent 的能力审批：能调哪些领域 MCP 由 `ai4-ujvn` 的开放面决定，套件只按模板写好配置。

### 交付形态

按 `toolkits/README.md` 的约定，套件是可打包发给 Agent 或人的一组文件（skills + MCP 配置 + hooks + 模板）。本票定的是内容与结构，打包脚本另行决定。

## Acceptance Criteria

- [ ] 套件包含 Gateway 模板、Agent 定义模板、初始化脚本、使用说明四部分，结构写明
- [ ] 明确模板基线是 `sci-weave/task-agent/` 的现有实现，不另写一套
- [ ] 明确套件不负责部署、不托管凭据、不包含中央侧组件
- [ ] 明确 `.env.example` 需要哪些变量（队列地址、数据库位置、持久目录、领域 MCP 地址）
- [ ] 使用说明能让研究员在无额外帮助的情况下建出一个能连上中央队列并提交草稿的 agent

## Notes

**2026-10-21T22:43:00Z**

来源：2026-10-21 讨论。Project Owner 提出 task-agent 应「提供技能来建立新的 task-agent」。此前全仓库没有票承载这件事，`researcher-agent-toolkit/deploy-task-agent/` 目录为空。

与 `ai4-v19u`（Agent 套件接入与协作边界分支）的关系：后者定套件的职责边界与接入方式，本票是它下面的一个具体套件。若 `v19u` 负责人认为应作为其子票，可调整层级。
