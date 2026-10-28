---
id: ai4-0wg0
status: in_progress
deps: []
links: [ai4-8d9j, ai4-fm4a, ai4-349h, ai4-japd]
created: 2026-10-28T06:41:45Z
type: chore
priority: 2
assignee: Frank Qi
parent: ai4-yidf
tags: [toolkit, suite, centre-agents, deployment]
---
# 中央 Agent 套件退场：搬迁停滞体检脚本与判据文本，删除 toolkits/centre-agent-toolkit

中央 Agent 的能力描述（definitions/）、MCP 卡片（libs/mcp-libs/）、判据（rules/）已经全部在 centre-control/centre-agents 里与服务同源；`toolkits/centre-agent-toolkit` 剩下的只有：5 份人读技能、一个只读停滞体检脚本、一套 systemd 用户级部署路径，以及一份与 centre-stack 相矛盾的 .env.example（网关端口 8711 vs 8760，单 SCIWEAVE_DOMAIN_MCP_URL vs 每域一套）。

ADR-0006 之后中央服务由 centre-stack 单容器 supervisord 托管，套件的 systemd 路径已被取代。留着它等于给同一套服务留第二份配置真相。

但直接删除会静默丢掉两样东西：唯一能发现 ingest 消费者停摆的 cron/prereview-sweep.sh，以及 merged-candidate / invalidation 两块当前 5 步 Chain 里没有对应实现的判据文本。因此先搬迁，再删除目录。

## Acceptance Criteria

- [ ] cron/prereview-sweep.sh 迁入 centre-agents/ops/，契约不变：只读、退出码 0/1/2、空表不算停滞，域健康探测覆盖 Mapping 与 Wiki 两个域
- [ ] 五份 SKILL.md 的判据与边界并入 docs 权威文档，含 merged-candidate 与 invalidation 两块当前 Chain 未实现的部分
- [ ] toolkits/centre-agent-toolkit 删除，仓库内无悬空引用
- [ ] toolkits/README、docs/data-flow/centre-agent.md、docs/验证命令.md 与 suitecheck 注释同步
- [ ] suitecheck check ../ 两个套件通过，suitecheck 与 centre-agents 回归结果不变
- [ ] ai4-8d9j 作废并记录；ai4-fm4a、ai4-349h 的相关裁决按属人规则加注修订，不覆盖原文

