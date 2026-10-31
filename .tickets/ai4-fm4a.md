---
id: ai4-fm4a
status: in_progress
deps: []
links: [ai4-jfvy, ai4-nj9r, ai4-8yk5, ai4-0fwc, ai4-x0ay, ai4-a2ba, ai4-he04, ai4-0wg0, ai4-8d9j, ai4-349h, ai4-japd, ai4-sman, ai4-jckq]
created: 2026-10-28T00:24:02Z
type: epic
priority: 1
assignee: Frank Qi
tags: [toolkit, suite, agent]
---
# 三个 Agent 套件落成为可安装形态：研究员 / 中央调度 / 项目负责人

「套件」在 `sci-weave/toolkits/README.md` 里的定义是 **skills + MCP + hooks/extensions + cronjob
的集合，不是每一个都必须**；目标是「上传一个套件 zip 给 Agent，他能自动安装使用」。
在此之前仓库里只有目录和标题：`centre-agent-toolkit/` 一行 README，`project-owner-agent-toolkit/`
两行 README 加一个空目录，`researcher-agent-toolkit/` 只有 `deploy-task-agent/`。

本票把四个角色之间的边界落成可执行的形态。四个角色是 2×2：

|  | 机器 | 人 |
| --- | --- | --- |
| 端侧 | Task Agent（研究员的机器上） | Researcher（人 + 自己的 Codex） |
| 中央 | Centre Agent（中央服务器） | Project Owner（人 + 自己的 harness） |

套件三个，不是四个：Task Agent 由研究员在自己的机器上部署，它的运行时、服务模板、libs
和技能都在 `researcher-agent-toolkit/deploy-task-agent/` 里，不单独成套件（原
`task-agent-toolkit/` 已删除）。

## 每个套件凭什么不一样

差别不在工具多少，而在**谁能把什么变成正式事实**：

| 套件 | actor | 能做 | 不能做 |
| --- | --- | --- | --- |
| `researcher-agent-toolkit` | `researcher` | 提交候选、审自己的稿、起草、部署 Task Agent | 批准成正式版本、预审、合并候选 |
| `centre-agent-toolkit` | `centre` | 预审候选、冲突矩阵、合并候选、失效标记 | 进草稿箱、formalize、派发任务 |
| `project-owner-agent-toolkit` | `project_owner` | formalize / 退回 / 驳回、派发根任务、登记人与 Agent | 预审、合并候选 |

能力上限由 `suitecheck` 在静态校验里强制：

| actor | 允许声明的能力 |
| --- | --- |
| `machine` | `read` |
| `researcher` | `read`, `candidate_submit` |
| `centre` | `read`, `centre`, `prereview_log`, `merged_candidate` |
| `project_owner` | `read`, `candidate_submit`, `candidate_review`, `formalize` |

负责人手里没有 `centre`（否则他能一次读到所有域的全部候选，预审和裁决合成一个人）；
中央 Agent 手里没有 `formalize`（同理）；研究员手里两者都没有。

## Acceptance Criteria

- [x] 每个套件有 `suite.yaml`，字段集合封闭，`actor` 与 `mcp[].capabilities` 不越界
- [x] 每个技能一个 `<技能名>/SKILL.md`，frontmatter 有 `name`（带套件前缀）与 `description`
- [x] 每个 MCP 一张 `mcp/<服务名>/mcp.json`，`name`/`transport`/`endpoint.url_env` 齐全
- [x] 每个套件有 `install.sh` 与 `check.sh`，`check.sh` 用 0/1/2 区分「就绪/未装/装了不可用」
- [x] `suitecheck` 能对三个套件一起做静态校验并通过（含跨套件技能重名）
- [x] `centre-agent-toolkit` 的常驻单元与只读体检脚本可安装、可执行
- [x] `docs/data-flow/centre-agent.md` 与 `sci-weave/toolkits/README.md` 与实际一致
- [x] 新增工单补齐 `docs/tickets/meta/<id>.toml`

## Notes

**2026-10-28T00:40:00Z**

三个套件与 `suitecheck` 已落成。校验：

```bash
cd sci-weave/toolkits/suitecheck
uv run python -m suitecheck.cli check ../
# centre-agent-toolkit (machine/centre)              ok
# project-owner-agent-toolkit (human/project_owner)  ok
# researcher-agent-toolkit (machine/researcher)      ok
# 3 suites together                                  ok
```

`suitecheck` 自身 `uv run python -m unittest discover -s tests -q` → 27 passed。

已知的取舍：

1. **套件只发布配置，不发布中央源码。** `centre-agent-toolkit/bin/start-ingest` 读
   `SCIWEAVE_CENTRE_AGENTS_HOME` 后在那里跑 `uv run`，因为 ADR-0002 让两侧 work-agent
   代码库保持分开。把源码打进 zip 会让「哪一个 checkout 在跑」变成两个答案。
2. **`create_merge_request` 是这次补的**（另见 `ai4-8yk5`）。没有它，Project Owner 套件的
   `decide-candidate` 技能整条链是假的：能预览、不能送决定。
3. **manifest/ZIP 的自动打包仍未做**，见 `ai4-nj9r`。当前形态是「拷目录 / 打普通 zip」，
   `install.sh` 自己不需要额外格式。

遗留风险：`researcher-agent-toolkit/deploy-task-agent/runtime/src/work_agent_runtime/skills.py`
是这次新增的技能加载器，其 12 个用例覆盖了一层深度、缺失 frontmatter 与重名，但没有覆盖
「技能目录里塞了子目录」这种畸形树。

## Notes

- 2026-10-28：三轮完成，PR https://gitee.com/qi-yueran/ai4science/pulls/56 。8 条验收标准全绿，`suitecheck check` 对三个套件 0 finding。
- `suitecheck` 的能力上限从文档搬进了静态校验：`actor` 决定允许声明哪些 `capabilities`，越界即报错。这条是「套件凭什么不一样」那张表唯一有强制力的地方。
- `centre-agent-toolkit` 后续把 MCP 卡片移交给服务侧（`ai4-349h`）：卡片描述的是服务的能力，跟着服务源码走，套件只剩「怎么装起来、怎么体检」。`suite.yaml` 的 `mcp:` 因此变成空列表，`suitecheck` 的 `suite_empty` 相应放宽到「skills 与 mcp 都空才算空」。
- 遗留：`ai4-sue2`（卡片令牌不进请求头）、`ai4-japd`（ingest 不在 supervisord 里）、`ai4-22mr`（PO 读不到预审报告）三张票记的是这套东西真机联调前必须处理的缺口。

**2026-10-28T06:46:45Z**

2026-10-28：`ai4-0wg0` 推翻了本票的一条验收与一条已知取舍，按属人规则在此记录，不覆盖原文。

1. **验收「`centre-agent-toolkit` 的常驻单元与只读体检脚本可安装、可执行」作废。** 常驻单元与 `bin/start-*` 属于 ADR-0006 之前的用户级 systemd 部署路径，与「单容器 supervisord」是两套答案；套件目录已删除，体检脚本迁到 `centre-agents/ops/prereview-sweep.sh`，由 `gateway/ingest/tests/test_prereview_sweep.py` 按退出码钉住。其余六条验收不受影响。

2. **Notes 里「三个套件」的说法作废，现为两个。** 套件的判据不变：差别在谁能把什么变成正式事实。中央 Agent 不再是套件，而是 `centre-stack` 里的服务，识别依据是 `docs/data-flow/centre-agent-prereview.md` 与 `centre-agents/definitions/`。

3. **`suite_empty` 的放宽保留，理由改写。** 放宽不再由某个具体套件背书，而是「只发布配置、卡片属于被配置服务的源码」这种通用形状；当前两个套件都有卡片，这条规则留作约束。
