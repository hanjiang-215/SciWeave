# 中央调度 Agent 的工作套件

装在中央服务器上，以 `centre` 身份工作：订阅候选事件与正式版本发布事件，拉全量候选快照做预审，
把报告追加到领域治理日志，判定失效，必要时合成混合候选，并在完成或受阻时通知 Project Owner。

**它读得到所有域的候选，但一个都不能批。** 这条线不是约定，而是能力上限：本套件声明的
`mcp[].capabilities` 里没有 `formalize`，`suitecheck` 会拒绝越界的清单。

## 装在哪、不装什么

套件**不打包中央服务的源码**。中央服务器本来就有 `sci-weave/centre-control/centre-agents`
的检出，`ADR-0002` 又明确要求 Task Agent 与 Centre Agent 两份源码互不 path 依赖。
再复制一棵树进来，只会让同一份服务有两个版本。

所以套件装的是服务仓库里没有的东西：

| 装 | 说明 |
| --- | --- |
| `bin/start-ingest`、`bin/start-mcp` | 两个常驻角色的入口，从 `.env` 读 `SCIWEAVE_CENTRE_AGENTS_HOME` 找到服务源码并跑在它的 uv 环境里 |
| `systemd/` | 两个 user 级 unit；install.sh 会把 `%h/.sciweave/centre` 换成实际目标 |
| `cron/prereview-sweep.sh` | 只读的停滞检测；**不写**任何治理日志 |
| `<skill>/SKILL.md` | 5 个技能，装到 `$SCIWEAVE_CENTRE_SKILLS_HOME`（默认 `~/.sciweave/centre-skills`） |
| `mcp/` | 5 张卡片：两个领域 MCP、registry、email-service、处置面 |
| `.env.example` | 只有变量名和示例，没有令牌 |

不装：预审判据文件。规则是 `<version>.json`，受 Git 版本化，由领域 MCP 经
`SCIWEAVE_MAPPING/WIKI_PREREVIEW_RULES_DIR` 解析。套件复制一份就变成第三份真相。

## 五个技能

| 技能 | 管什么 | 关键约束 |
| --- | --- | --- |
| `audit-candidate-branches` | 先核对分支本身：`snapshot_status`、head、基座、来源 | 快照读不出来时一条结论都不许下，包括「看起来没问题」 |
| `prereview-checks` | 四项检查、判据版本、报告怎么写 | 格式/引用/依赖已被写入时拒绝，不再重判；`stale`/`conflict` 是报告事实，不是 Proposal 状态 |
| `conflict-matrix` | 同批同时点候选在同一个逻辑对象上的重叠 | 一轮预审只调一次 `list_reviewable_candidates`，否则「同时点」不成立 |
| `invalidation` | `head_moved` / `base_moved` 的追加判定 | 失效既不放行也不冻结全体；`head_moved` 必须带新报告 |
| `merged-candidate` | 合成新候选分支 | 只新建、不改源、不得二次混合；真冲突时混合是错的 |

## 能力上限

| MCP | 能力 | 为什么就这些 |
| --- | --- | --- |
| `research-mapping` | `read` `centre` `prereview_log` `merged_candidate` | 没有 `formalize`：预审和裁决合成一个人，两套套件就没意义了 |
| `research-wiki` | 同上 | 同上；Wiki 侧的裁决工具是 `decide_wiki_review`，同样不在卡片里 |
| `registry` | `centre` | 只读 `get_agent_registration` 与 `health`，判断「要通知的那个 Agent 是不是在线」 |
| `email-service` | `read` | 只发 `prereview_completed` 和 `agent_unavailable` 两类通知 |
| `disposition` | `read` | 观察与处置自己的执行；没有 `submit_owner_command`，不发起执行 |

## 安装

```bash
./install.sh
vi ~/.sciweave/centre/.env            # 至少填领域 MCP 地址/令牌、gateway 令牌、队列组与订阅主题
systemctl --user enable --now sciweave-centre-agent-ingest.service
systemctl --user enable --now sciweave-centre-agent-mcp.service
./check.sh
```

`install.sh` 幂等：重复执行只换代码与 unit，保留已有 `.env`、`SCIWEAVE_INGEST_DB` 和 gateway SQLite。

`check.sh` 只读，退出码分三档（0 就绪 / 1 没装全 / 2 装了但不能跑）。它会专门检查两件
「看起来正常但什么也不做」的状态：

- `SCIWEAVE_QUEUE_BOOTSTRAP_SERVERS` 为空 ⇒ ingest 退回 `FakeQueue`，systemd 显示 active，
  但一条治理事件都不消费；
- 预审规则目录里没有 `<version>.json` ⇒ 每次 `append_prereview_log` 都返回
  `rule_set_missing`，套件能启动却记不下任何报告。

## 两个常驻进程

```
治理事件 topic ──► ingest（gateway/ingest）──► 领域管理 MCP
                       │                      （append_prereview_log / create_merged_candidate）
                       └── 共享 SQLite ◄── mcp（处置面：query/list/cancel/answer/review）
```

- **ingest** 出站连队列，不需要入站可达地址。offset 逐条提交，崩溃最多重放一条。
  一个 `SCIWEAVE_DOMAIN_MCP_URL` 只对一个域工作，所以 Mapping 与 Wiki 各起一份，
  用不同的消费者组与 topic 前缀区分。
- **mcp** 是处置面，只给运维看中央执行，绑定回环地址即可。它不创建执行，
  也不提供 `accept`：中央的工作来自候选事件，不来自命令。

## 停滞检测

`cron/prereview-sweep.sh` 每 10 分钟跑一次，只读：

- `processed_events` 最新 `handled_at` 超过 `SCIWEAVE_PREREVIEW_SWEEP_MAX_AGE_SECONDS`
  （默认 1800）⇒ 退出 1，说明消费者停了；
- 空表不算停滞——刚装好还没收到事件时，它看起来就是这样；
- 领域 MCP 的 `/health` 探不通 ⇒ 退出 1。消费者活着但唯一写入口挂了，比消费者挂了更糟：
  它会一路提交 offset，把「没记下来」变成「已经处理过」。

为什么要有这个：**唯一无法发现自己缺席的组件就是消费者本身。** 它停了，候选会安静地堆成
`missing_report`，Project Owner 看到的是一排没人动的候选，而不是一条告警。

## 边界

不批候选、不进草稿箱、不派发任务、不判断「下一步该谁动」、不一次调用同时改两个域、不修源候选、
不改历史报告、不二次混合。
