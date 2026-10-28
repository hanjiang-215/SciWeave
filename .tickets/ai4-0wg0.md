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

- [x] cron/prereview-sweep.sh 迁入 centre-agents/ops/，契约不变：只读、退出码 0/1/2、空表不算停滞，域健康探测覆盖 Mapping 与 Wiki 两个域
- [x] 五份 SKILL.md 的判据与边界并入 docs 权威文档，含 merged-candidate 与 invalidation 两块当前 Chain 未实现的部分
- [x] toolkits/centre-agent-toolkit 删除，仓库内无悬空引用
- [x] toolkits/README、docs/data-flow/centre-agent.md、docs/验证命令.md 与 suitecheck 注释同步
- [x] suitecheck check ../ 两个套件通过，suitecheck 与 centre-agents 回归结果不变
- [x] ai4-8d9j 作废并记录；ai4-fm4a、ai4-349h 的相关裁决按属人规则加注修订，不覆盖原文


## Notes

**2026-10-28T06:52:36Z**

**2026-10-28T06:58:00Z（实施与验证）**

分支 `feature/frank-qi`，四个提交：

| 提交 | 内容 |
| --- | --- |
| `1496b7d` | `refactor(toolkits)`：删套件、搬 sweeper、加 `test_prereview_sweep.py`、改写 suitecheck 两处注释 |
| `5ebd160` | `docs(centre-agents)`：四处文档指向修正 + 两份规格的状态修订 |
| `857855b` | `chore(tickets)`：本票 + 四张关联票的加注 |
| `846884f` | `docs(centre-agents)`：五份 SKILL.md 并入 `centre-agent-prereview.md` |

**verbs 变了三处，逐条说明为什么改：**

1. 数据库不存在：exit 1 → **exit 2**。「停了」与「配错了」会把运维引到不同地方，而一个在全新主机上就喊停摆的体检脚本一周内就会被静音。
2. 域名健康探测：单域 → **两域**。`SCIWEAVE_DOMAIN_MCP_URL` 只对一个域工作，Mapping 答得上来说明不了 Wiki；现在按 `SCIWEAVE_PREREVIEW_SWEEP_MCP_URLS` → `RESEARCH_MAPPING_MCP_URL`+`LLM_WIKI_MCP_URL` → 单个 `SCIWEAVE_DOMAIN_MCP_URL` 的顺序解析。
3. 健康行输出带上 `last status`：一行 `alive` 看不出这个消费者一直在记 `error`。

前两条改的是契约，所以 `ai4-fm4a` 的修订注记里写的「契约不变」不准确——准确说法是「只读、0/1/2 三档、空表不算停滞」不变，其中 1 与 2 的边界按上面收紧。

**验证**（`scripts/ci.sh --skip-web`，19 个项目）：

```
gateway/ingest           PASS  20 passed（11 → 20，新增 9 条 sweeper 用例）
centre-agents/worker     PASS 103 passed
suitecheck               PASS  28 passed
research-map             PASS 132 passed  5 skipped
research-wiki            PASS 141 passed 12 skipped
其余 14 个项目            PASS
compileall               PASS 18 个 src 目录
git diff --check         PASS
合计 1319 passed / 22 skipped，全部通过
```

`suitecheck check ../` 对两个套件 0 finding；`check ../researcher-agent-toolkit` 与 `check ../project-owner-agent-toolkit` 分别 0 finding。

**遗留**（不阻塞本票关闭，已在关联票记）：

- ingest 现在全仓没有启动入口，`ai4-japd` 的优先级含义变了（已加注）。
- `ops/prereview-sweep.sh` 在容器里没有调度者：supervisord 只托管常驻进程，它需要宿主机 cron 或一个 sidecar。这一点留给 `ai4-japd` 一并处理，本票只保证脚本本身可用且被测试钉住。
