# 项目负责人的 Agent 套件

装进负责人**自己的** harness（Codex / Cursor / WorkBuddy / fast-agent），以 `project_owner`
身份工作：读正式路线与候选，预览改动与影响范围，记录批准/退回/驳回，把批准的候选正式化，
路线需要继续时派发根任务。

负责人这个角色手里握着**最终裁决**，所以它手里没有预审：没有 `centre` 能力，
也没有 `list_reviewable_candidates` 那张全量快照读。预审和裁决合成一个人，两套套件就没有分别了。

## 这是个「human」套件

没有常驻服务、没有 worker、没有 cron。安装脚本只做三件事：

| 装 | 到哪 |
| --- | --- |
| 6 个技能 | `$SCIWEAVE_OWNER_SKILLS_HOME`（默认 `~/.sciweave/owner-skills`），**扁平一层** |
| 5 张 MCP 卡片 | `$SCIWEAVE_OWNER_CONFIG_HOME/mcp/<服务>/mcp.json` |
| 一份 fast-agent 定义 | `$SCIWEAVE_OWNER_CONFIG_HOME/fast-sci-agent/owner-agent.yaml` |

用 Codex / Cursor / WorkBuddy 的负责人只需要技能与卡片；用 fast-agent 的再加上那份定义。

## 六个技能

| 技能 | 管什么 | 最容易踩的坑 |
| --- | --- | --- |
| `impact-preview` | 读 `changes`、`affected_objects`、`route_impact` | 把 `preview_candidate` 的 `passed` 当成「可以批准」 |
| `decide-candidate` | 预览 → buffer → 记录决定 → 正式化 | 以为 `record_review(approved)` 已经改了正式图 |
| `request-revision` | 退回并让退回可执行 | 用 `rejected` 表达「先别做」；`dedupe_key` 漏了 head |
| `handle-merge-candidate` | 混合候选的作者是 `merged:` 开头 | 通知发给那个标记；以为源作者能改它 |
| `dispatch-root-task` | 启动路线，判断 `accepted=false` 缺什么 | 把「未知」当成「不可用」，去修一个没坏的映射 |
| `notification-status` | 逐收件人看送达状态 | 对 `permanent_failure` 重发同一条通知（永远不会生效） |

## 五个 MCP

| MCP | 能力 | 为什么 |
| --- | --- | --- |
| `research-mapping` | `read` `candidate_submit` `candidate_review` `formalize` | 没有 `centre`：读全量候选会把裁决变成预审 |
| `research-wiki` | 同上 | 同上；Wiki 侧的决定工具是 `decide_wiki_review` |
| `coordinator` | — | 只有一个工具 `dispatch_root_task`，其余由 Kafka 事件驱动 |
| `registry` | — | 按 `caller_type` 授权，不按领域能力；令牌必须是 `project_owner` |
| `email-service` | `read` | 只发 `candidate_revision_requested` / `candidate_rejected` |

`submit_candidate` / `submit_wiki_candidate` 在卡片里，因为路线要继续时负责人得自己写下一步。
那不会绕过预审：负责人写出来的东西仍然要过中央 Agent，再以候选身份回到他面前。

## 安装

```bash
./install.sh
vi ~/.sciweave/owner/.env      # 五个 MCP 的地址与令牌
./check.sh
```

`check.sh` 会额外检查一件事：令牌是不是还停在 `.env.example` 的 `replace-with-*`。
只检查「非空」的话，一个照抄示例的配置看起来完全正常，直到第一次调用 401。

## 技能目录为什么必须是一层

`fast-agent` 的 `SkillRegistry._load_directory` 只往下走一层。把
`~/.sciweave/owner-skills` 整个套件目录指给 harness，它会**加载零个技能并且不报错**。
所以 `install.sh` 把每个技能平铺到 `<skills-home>/<skill>/SKILL.md`，`check.sh` 逐个文件确认。

## 边界

不预审、不进草稿箱、不改候选分支、不重写历史审核事件、不替研究员部署 Task Agent、
不用新的 `operation_id` 重试正式化、不派发非根节点。
