---
id: ai4-japd
status: open
deps: []
links: [ai4-349h, ai4-0wg0, ai4-8d9j, ai4-fm4a]
created: 2026-10-28T05:58:20Z
type: bug
priority: 1
assignee: Frank Qi
parent: ai4-yidf
tags: [centre-control, centre-agents, infra, deployment]
---
# gateway/ingest 在 centre-stack 里没有 supervisord 程序

centre-stack/supervisord.conf 有 12 个程序，没有 ingest。而 `gateway/ingest` 是「治理事件 → 执行记录」这条链的入口：没有它，容器里的中央 Agent 收不到任何候选事件，只能等 gateway/mcp 被人手工调用。

ai4-qula 修的是消费器本身（落库 + 派发），它默认 ingest 已经在跑。这张票修的是「谁来启动它」：一条 supervisord program、一个 compose 环境块（Kafka bootstrap / 消费组 / 领域 MCP 地址与令牌 / 去抖窗口），以及 README 的进程表。

注意 Mapping 与 Wiki 各需要一份 ingest（一个 SCIWEAVE_DOMAIN_MCP_URL 只对一个域工作），消费组与 topic 前缀不同。这是两条 program，不是一条。

## Acceptance Criteria

- [ ] `supervisord.conf` 里有两个 ingest program（Mapping / Wiki），各自有停止优先级与日志路径
- [ ] `compose.yaml` 有对应的环境变量块，地址与令牌走 `.env` 而不是字面量
- [ ] 容器内两个 ingest 都起来并稳定运行，`supervisorctl status` 全部 RUNNING
- [ ] README 的进程与端口表补上这两个角色
- [ ] 有测试或只读脚本断言 `supervisord.conf` 与 compose 的变量名对得上

## Notes

- 2026-10-28：建票。`docs/superpowers/specs/2026-10-28-centre-agent-definition-layer-alignment-design.md` 的 Out of Scope 已把这条记为「独立缺陷」；`ai4-qula` 只修消费器本身。


**2026-10-28T06:46:50Z**

2026-10-28：本票的紧迫性上升，范围不变。

`ai4-0wg0` 删除了 `toolkits/centre-agent-toolkit/`，其中 `bin/start-ingest` 是此前全仓唯一能拉起 `sciweave-task-agent-gateway-ingest` 的入口。现在 ingest **没有任何启动入口**：`centre-stack/supervisord.conf` 没有它，套件的 systemd unit 也没了。消费者代码与测试（20 个用例）都在，只是没人启动。

这不改变本票的验收，但把它的优先级从「补一个 program」变成「这条链在容器里彻底没有入口」。两条 ingest program（Mapping / Wiki）的落地要一并处理：
- 消费组与 topic 与端侧订阅者不同（`SCIWEAVE_QUEUE_GROUP_ID`、`SCIWEAVE_SUBSCRIBER_TOPICS`）；
- `SCIWEAVE_INGEST_DB` 必须落在 `/data/centre-agents/` 具名卷内，`ops/prereview-sweep.sh` 按这个路径判断消费者是否还活着；
- 域 MCP 地址用容器内回环（`http://127.0.0.1:8710/mcp`、`http://127.0.0.1:8720/mcp`），token 用 `CENTRE_TOKEN_CENTRE_AGENT`。

停滞体检脚本现在随 `centre-agents` 源码走，进镜像后可用 `SUPERVISOR` 之外的 cron 或在宿主机上定时执行；这一点请在实现本票时一并决定。
