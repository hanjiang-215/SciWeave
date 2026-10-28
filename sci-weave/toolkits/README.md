# Agent套件

所谓的套件，指的是 skills + MCP + hooks/extensions + cronjob 的集合
（不是每一个都必须）

目标，上传一个套件zip给Agent，他能自动安装使用

## 三个套件

| 套件 | 装在哪 | 以谁的身份调用 | 能做 | 不能做 |
| --- | --- | --- | --- | --- |
| `researcher-agent-toolkit/` | 研究员自己的机器（个人 Agent + 自己部署的 Task Agent） | `researcher` | 提交候选、审自己的稿、起草、部署 Task Agent | 审批成正式版本、预审、合并候选 |
| `centre-agent-toolkit/` | 中央服务器（中央 Agent 本身跑在 `centre-stack` 里，套件只装它的配置与体检） | `centre` | 预审候选、冲突矩阵、合并候选、失效标记 | 进草稿箱、formalize、派发任务 |
| `project-owner-agent-toolkit/` | 负责人自己的机器（自己的 harness） | `project_owner` | formalize / 退回 / 拒绝候选、派发根任务 | 预审、合并候选 |

`task-agent-toolkit/` 已移除：Task Agent 由研究员在 `researcher-agent-toolkit/deploy-task-agent/`
里部署，它的运行时、服务模板、libs 和技能都在那里，不再单独成套件。

三个套件当前的内容：

| 套件 | 技能 | MCP 卡片 | hook | cron | 安装后跑什么 |
| --- | --- | --- | --- | --- | --- |
| `researcher-agent-toolkit` | 8（+ `deploy-task-agent` 侧 6） | 7 | 1（`harness-open`） | — | 个人 Agent 的会话；Task Agent 另行部署 |
| `centre-agent-toolkit` | 5 | 0（见下） | — | 1（`prereview-sweep`） | 两个常驻单元：`ingest` 与 `mcp` |
| `project-owner-agent-toolkit` | 6 | 5 | — | — | 负责人自己的 harness，无常驻进程 |

`centre-agent-toolkit` 是唯一声明 0 张卡片的套件：中央 Agent 是服务器上的一个**服务**，
它连哪些 MCP、每一步说什么，写在 `centre-agents/definitions/` 与
`centre-agents/libs/mcp-libs/` 里，与被描述的服务同源（`ai4-349h`）。套件这边只说
「怎么把它装起来、怎么定期体检」，所以没有卡片可指。

套件的差别不在「工具多少」，而在**谁能把什么变成正式事实**：研究员能提交不能批准，
中央 Agent 能预审不能正式化，负责人能正式化不能预审。任何一套里出现越界的工具，
先看 `suite.yaml` 的 `actor` 是不是写错了。

## 套件长什么样

每个套件目录一份 `suite.yaml`，其余都是它声明的载荷。技能就是套件根下的
`<技能名>/SKILL.md`，MCP 卡片在 `mcp/<服务名>/mcp.json`（套件声明 0 张卡片时整段写
`mcp: []`）——和已有的空目录一致，不再另起一层 `skills/`：

```yaml
suite: researcher-agent-toolkit   # 目录名；技能名以它为前缀
role: machine                     # machine | human —— 装在哪
actor: researcher                 # 以谁的身份调 MCP；决定能力上限
title: 研究员的工作套件
version: 0.1.0
summary: >
  一句话说明这个套件替谁干什么。
boundary:
  may_modify: []                  # 允许改的东西
  must_not: []                    # 明确不碰的东西
requires:
  env: [DRAFT_BUFFER_MCP_URL]     # 需要的变量名，只写名字
  services: []                    # 需要先跑起来的服务
skills:
  - name: submit-candidate
    path: submit-candidate
mcp:
  - name: draft-buffer
    card: mcp/draft-buffer/mcp.json
    capabilities: [read, candidate_submit]
hooks:
  - name: check-services
    path: hooks/check-services.sh
    event: harness-open
cron:
  - name: conflict-sweep
    path: cron/conflict-sweep.sh
    schedule: "*/5 * * * *"
install: [./install.sh]
check: [./check.sh]
```

`actor` 决定 `mcp[].capabilities` 的上限，校验器会拒绝越界：

| actor | 允许声明的能力 |
| --- | --- |
| `machine` | `read` |
| `researcher` | `read`, `candidate_submit` |
| `centre` | `read`, `centre`, `prereview_log`, `merged_candidate` |
| `project_owner` | `read`, `candidate_submit`, `candidate_review`, `formalize` |

这张表就是四个角色之间那条线：负责人手里没有 `centre`（否则他能一次读到所有域的全部候选），
中央 Agent 手里没有 `formalize`（否则预审和裁决合成一个人），研究员手里两者都没有。

## 校验

```bash
cd sci-weave/toolkits/suitecheck
uv run python -m suitecheck.cli check ../
uv run python -m suitecheck.cli run check ../centre-agent-toolkit
```

`check` 只做静态校验：manifest 字段、技能 `SKILL.md` 的 frontmatter、MCP 卡片的
`name`/`transport`/`endpoint`、hook 可执行位、能力上限、install/check 命令是否声明。
`run` 才会真的执行；`run install <dir> --dry-run` 只打印。

安装到目标机器上的是套件目录本身（打成 zip 上传即可），`install.sh` 与 `check.sh`
由安装它的 Agent 执行，不需要额外的打包格式。
