# AI4Sci / SciWeave 项目审查（2026-10-27）

- 审查日期：2026-10-27
- 审查对象：`D:\project\AI4Sci`（分支 `feature/hanjiang`，HEAD `8ba0e0a`，工作区干净）
- 对比基线：[`AI4Sci-review-2026-10-22.md`](AI4Sci-review-2026-10-22.md)
- 审查方式：实跑全量回归矩阵、连真实 TerminusDB / Redpanda 跑集成用例、实跑演示看板链路、扫描工单与文档、核对分支与凭据卫生
- 说明：本文是时点快照，数字与结论以当日 HEAD 为准

---

## 一、结论摘要

1. **五天里项目从「文档强、代码弱」翻转为「可运行平台」。** 10-22 时只有两个领域治理内核与一个过期 Gateway；现在 `centre-control` 下已有 8 个可运行子项目、端侧套件、共享协议包与 CI 矩阵，Python 源码 20,464 行、测试 16,161 行、861 项用例全绿。
2. **真实存储链路是通的，不是 mock 出来的。** 我在本机 TerminusDB（v12.0.8）+ Redpanda（v24.3.7）实跑：research-map 127 passed、research-wiki 148 passed、coordinator 的 handoff 端到端 1 passed（治理事件 → 正式快照 → `task_handoff_ready` 发布）。这三个数字比任何票面记录都硬。
3. **工单体系已经从「规划」切换到「收口」。** 209 张票、204 张 closed、活跃只剩 5 张（3 open / 2 in_progress），`ticket_index.py check` 除生成物过期外无错误。10-22 说的「25/31 活跃压在一个人身上」已经不存在。
4. **真正的交付风险不在代码，在两件赛事硬门槛上：** ①SciencePal 至今只承担了 smoke 级 run（`hello.txt` / `probe.txt`），T1 数据检查与 T2 基线分类仍由本机标准库脚本完成；②赛事要求「评审期链接可访问」，而生产部署与公网暴露在 `docs/TECH_STACK.md` 里仍是未确定项，当前只能本机演示。
5. **CI 现在有矩阵，但没有任何地方真正执行它。** `scripts/ci.ps1` 本地可跑；`.github/workflows/ci.yml` 在 Gitee 上不会触发。后果是本轮抓到的 Linux-only 红测试（`ai4-grlc`）能一路活到今天——没人会在 Linux 上跑它。
6. **审查本身发现 11 处需要修的工程缺陷**（见 4.2）。其中 CI 汇总把「恰好一个阶段失败」报成「全部通过」、以及 `shared/message-envelope` 写了 87 项测试却零生产引用这两条，会直接影响后续所有人的判断。

---

## 二、实测结果

### 2.1 回归矩阵（本机，Windows，Python 3.11/3.14，uv 0.10.7）

`scripts\ci.ps1` 全量执行，**21/21 阶段通过，861 项用例通过，22 项默认跳过**。

| 子项目 | 结果 | 耗时 |
| --- | --- | ---: |
| `humans/competition/demo-evidence` | 20 passed | 3.2s |
| `centre-control/buffer` | 28 passed, 3 skipped | 6.7s |
| `centre-control/centre-agents/gateway/ingest` | 11 passed | 3.3s |
| `centre-control/centre-agents/gateway/mcp` | 13 passed | 25.1s |
| `centre-control/centre-agents/gateway/subscriber` | 27 passed | 11.8s |
| `centre-control/centre-agents/worker` | 18 passed | 3.4s |
| `centre-control/coordinator` | 86 passed, 2 skipped | 11.1s |
| `centre-control/dashboard-api` | 17 passed | 5.5s |
| `centre-control/email-service` | 114 passed | 69.5s |
| `centre-control/registry` | 14 passed | 25.8s |
| `centre-control/research-map` | 124 passed, 5 skipped | 16.2s |
| `centre-control/research-wiki` | 136 passed, 12 skipped | 13.6s |
| `centre-control/shared/audit-trail` | 16 passed | 1.4s |
| `centre-control/shared/message-envelope` | 87 passed | 1.5s |
| `toolkits/.../custom-mcp/sciencepal-bridge` | 35 passed | 14.0s |
| `toolkits/.../custom-mcp/stdio-service` | 1 passed | 1.3s |
| `toolkits/.../runtime` | 106 passed | 14.1s |
| `web-ui`（vitest / vue-tsc + vite build） | 2/2 通过 | 6.2s / 12.1s |
| `git diff --check` | 通过 | — |

### 2.2 真实存储集成（显式开启）

本机容器 `ai4sci-terminusdb`（v12.0.8）与 `ai4sci-redpanda`（v24.3.7）均在运行，`http://127.0.0.1:6363/api/info` 返回 200。

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `research-wiki` 全量（`SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1`） | **148 passed** | 默认跑法下其中 12 项被跳过 |
| `research-map` 全量（同上） | **127 passed, 2 skipped** | 默认跑法下 5 项被跳过 |
| `coordinator/tests/test_handoff_e2e.py`（`+SCIWEAVE_RUN_KAFKA_INTEGRATION=1`） | **1 passed** | 真实 TerminusDB 建库播种 → 治理事件 → 正式快照 → 发布 `task_handoff_ready` |

这三条说明：领域治理内核、跨存储一致性、协调器派发链路与真实基础设施对得上。10-22「`shared/audit-trail` 写完没人用」也已闭合——research-map、research-wiki、registry、email-service 四个 `pyproject.toml` 都以 path 依赖引用它。

### 2.3 演示链路实跑

`scripts/demo-dashboard.ps1 -ResetSeed` 一次跑通：

```text
播种：formal_revision_id=rev-dashboard-x09yxnir016a，task_nodes=3，dependency_edges=2
看板：mode=live，mapping=fresh，项目/任务 1/3
快照：GET http://127.0.0.1:8702/api/dashboard/snapshot → 200
页面：GET http://127.0.0.1:5173/ → 200
```

**但 4 个数据源只活了 1 个**：`wiki`、`gateway`、`queue` 三个来源在快照里都是 `status=unavailable`、`error=来源地址未配置`。看板上表现为「部分来源」，不是故障，但与「看板能把整个平台看穿」的设计意图有差距——这三条来源的服务端能力都已实现（wiki 管理 MCP、subscriber 的 queue 看板、gateway 的 dashboard 片段），只是 demo-stack 没接。

### 2.4 工程卫生

- 无 `.env`、无令牌、无密钥入库；`git grep` 未命中 `sk-`/`ghp_`/私钥/明文密码。
- 被跟踪的最大文件是两个 `uv.lock`（约 610KB），符合预期。
- 工单索引一致性：`check` 报 3 个生成物过期（`INDEX.md`、`modules/governance.md`、`modules/agent.md`，均为不入库的本地生成物）与 1 条简介超长警告（`docs/tickets/meta/ai4-g6zi.toml` 为 72 字，建议 20–60 字），无失效引用、无缺失归属。
- 分支：`feature/hanjiang` 与 `origin/feature/hanjiang` 齐平，领先 `origin/develop` 10 个提交且不含落后；`origin/feature/frank-qi` +2、`origin/feature/hefan` +5、`qiyueran` / `zhanyunfei` 已全部并入 `origin/develop`。本地 `develop` 落后远端 209 个提交（只是没拉，不影响正确性）。PR 节奏正常，最近一条是 `!51`。

---

## 三、工单审查

### 3.1 规模与结构

| 模块 | 总数 | 已关闭 | 活跃 |
| --- | ---: | ---: | ---: |
| Agent 与消息协作 | 83 | 80 | 3 |
| 提案治理与审计 | 32 | 32 | 0 |
| Research Mapping | 24 | 23 | 1 |
| Gateway 与执行运行时 | 23 | 23 | 0 |
| 产品与需求 | 18 | 17 | 1 |
| 工程基础设施 | 15 | 15 | 0 |
| LLM-Wiki | 14 | 14 | 0 |
| **合计** | **209** | **204（97.6%）** | **5** |

活跃 5 张：

| 工单 | 状态 | 类型 | 负责人 | 还差什么 |
| --- | --- | --- | --- | --- |
| `ai4-aaff` | in_progress | prototype | hanjiang | 3–5 分钟计时演示、SciencePal 真实执行证据、驳回分支实演 |
| `ai4-jckq` | in_progress | feature | hanjiang | WorkBuddy/DSH 实际安装、T1/T2 真实执行 |
| `ai4-v869` | open | feature | hanjiang | 中央 MCP 公网端点（备选路径），本轮不阻塞 |
| `ai4-roow` | open | feature | hanjiang | 真实 run 的报告 → 草稿 → 候选 → 正式化全链（AC1/AC2/AC4） |
| `ai4-grlc` | open | bug | Frank Qi | 套件出厂四缺陷（红测试、env 缺项、YAML 重复、卡片描述） |

### 3.2 关闭质量

票面质量明显高于同类项目：`ai4-grlc`、`ai4-ceqq`、`ai4-bp6v` 这类票写清了复现命令、根因、Not in Scope 与「哪条验收没做、为什么」。**这是本项目最强的资产，比代码更值钱。**

但有一个系统性问题：**24 张已关闭的票验收项一条都没勾**（`ai4-0nuq`、`ai4-3xsp`、`ai4-68cv`、`ai4-83uk`、`ai4-8aa0`、`ai4-99ut`、`ai4-9wji`、`ai4-b8vm`、`ai4-bp6v`、`ai4-br61`、`ai4-ced7`、`ai4-ceqq`、`ai4-dhpv`、`ai4-eikj`、`ai4-jbci`、`ai4-mx7h`、`ai4-o806`、`ai4-sxpw`、`ai4-tb9k`、`ai4-vqkn`、`ai4-w333`、`ai4-wdvf`、`ai4-x6gd`、`ai4-xejt`）。其中多数是「做完没勾」（`ai4-bp6v` 已实测确认过一批），但状态与验收不一致等于把核实责任推给下一个人。另有一张 `ai4-ceqq` 是**诚实未勾**：真实 163 SMTP 投递缺授权码，票里写明了不当作通过——这种写法是对的，不该被批量「补齐」掉。

### 3.3 负载与所有权

活跃工单 5 张里 4 张在 hanjiang、1 张在 Frank Qi；`ai4-aaff` / `ai4-jckq` / `ai4-roow` / `ai4-v869` 其实是同一条 SciencePal 线的四张票，**整条赛事交付主线压在一个人身上**。这比 10-22 的「25/31 压一人」健康得多，但对最后 3 天仍是单点。

---

## 四、代码与架构

### 4.1 已落地的能力面（按对外入口）

| 子项目 | 对外形态 | 关键能力 |
| --- | --- | --- |
| `research-map` | 管理 MCP（Streamable HTTP）+ 看板来源 HTTP | 候选提交、预览、审阅、正式化、精确版本查询、预审日志、混合候选、失败恢复 |
| `research-wiki` | 同上 | Wiki 内容与资源引用、候选治理、资源资格审核与撤回、正式查询 |
| `buffer` | MCP（HTTP + stdio） | 草稿箱 7 工具、两命名空间、评审身份隔离 |
| `registry` | MCP + HTTP | 主体与端侧 Agent 登记、联系人查询、状态历史、幂等与审计 |
| `coordinator` | 常驻进程 + MCP + Kafka | 依赖重算、执行者选择、派发、重试上限、启动恢复、人工通知 |
| `email-service` | MCP | 真实 SMTP（ssl/starttls/none）、逐收件人重试、错误分类、`/health` sender 分项 |
| `centre-agents` | gateway/{ingest,mcp,subscriber} + worker | 消息消费、执行记录状态机、处置面工具、草稿写入、固定定义跑完一轮 |
| `dashboard-api` + `web-ui` | HTTP 聚合 + Vue 看板 | 四来源聚合、`mode=live/fixture`、5 个视图、source health |
| `shared/audit-trail`、`shared/message-envelope` | 共享包（path 依赖） | 调用账本；四类消息 payload、版本兼容校验、JSON 编解码 |
| `toolkits/researcher-agent-toolkit` | zip 套件 | runtime（fast-agent + 持久队列 + 草稿写入）、service-template（mcp/subscriber/worker）、sciencepal-bridge（5 工具、stdio/HTTP/CLI）、6 个 skill、标准 MCP 卡片 |

架构上与 ADR 一致的地方值得记一笔：**两套运行时代码不抽共享库**（ADR-0002）在代码里落实了——`centre-control/centre-agents/worker`（`store.py` 339 行 + `runtime.py` 162 行）与 `toolkits/.../runtime`（`durable.py` 282 行 + `runtime.py` 192 行 + `fast_agent_runtime.py` 191 行）是两份实现，行为对齐、源码独立。

### 4.2 需要修的缺陷

| # | 位置 | 问题 | 影响 |
| --- | --- | --- | --- |
| 1 | `scripts/ci.ps1:171` | 汇总用 `$results.Count - $failed.Count`，但当**只有一个**阶段失败时，`$failed` 是单个 `PSCustomObject`，`$failed.Count` 求值为空，于是打印「通过 21 / 共 21 个阶段」同时又列出「失败阶段：compileall」。我实测复现了这个语义（退出码仍是 1，所以门禁没坏，坏的是给人看的数字） | 以后任何人看 CI 摘要都会被误导成「全过」 |
| 2 | `research-wiki/tests/test_formalization.py:63` 与 `:101` | 两个方法同名 `test_same_operation_is_rejected_when_owner_approval_identity_changes`，后者覆盖前者；L63 那条（含通知失败与 `formalization_activated` 审计断言）**永不执行**。10-22 已提出，5 天未修 | 测试数量在骗人：`136 passed` 里少了这 1 条，且它守的正是通知失败路径 |
| 3 | `docs/ci.md:39` | 写「16 个测试位置、785 项用例通过」，实际 **17 个位置、861 项** | 文档落后于代码，评审时会被当成没跑过 |
| 4 | `sci-weave/centre-control/README.md` 表格 | 缺 `coordinator`、`email-service`、`shared/message-envelope` 三行（这三个都是已交付的活跃子项目） | 新人按 README 读，会以为中央控制面只有 6 个组件 |
| 5 | `docs/superpowers/specs/2026-10-21-mapping-wiki-formalization-delivery-design.md` | 状态仍是「待用户审阅」，而它描述的交付早已合并进 `develop`。10-22 已提出，未改 | 读文档的人无法判断这是已批准方案还是提案 |
| 6 | `sci-weave/task-agent/`（本机工作区） | 已从 Git 移除（0 个被跟踪文件），但本地目录仍在，只剩 `.venv`/`egg-info`/`.pytest_cache`，无任何 `.py` | ADR-0002 要求「两处都落地后删除」，现在两处都落地了；残留会误导 IDE 与导航 |
| 7 | `CHANGELOG.md` | 最后写入 2026-10-27 03:14，其后当天 113 个提交未收录；内容混入 `Bring origin/develop into the registry branch` 这类合并噪声 | 不能当发布日志用；提交前若要用需重跑 `git cliff` |
| 8 | `scripts/demo-dashboard.ps1` 收尾提示 | 打印 `停止 : pwsh scripts/demo-dashboard.ps1 -Stop`，而本机没有 `pwsh`（只有 Windows PowerShell 5.1） | 演示现场照抄会失败 |
| 9 | `shared/message-envelope` | 87 项测试全绿，但**生产代码零引用**：`git grep message_envelope -- '*.py' ':!*/tests/*'` 无命中。coordinator 的 `adapter_publisher.py`、`gateway/ingest`、service-template 仍各自手搓 dict | 与 10-22 时 `audit-trail` 的处境相同：写完没人用。区别是 `audit-trail` 已经接上了，这个还没有。消息协议一旦两边各自演化，信封的版本校验就形同虚设 |
| 10 | `toolkits/.../service-template/{worker,gateway/mcp,gateway/subscriber}` | 三个角色都只有 `src/main.py`，**没有 `pyproject.toml`**，不是可安装包 | 套件对研究员的承诺是「上传 zip 就能装就能跑」（`ai4-grlc` 的口径），而这三个入口目前只能靠 `PYTHONPATH` 手拼起来跑 |
| 11 | `buffer/src/draft_buffer/main.py:98` | `SCIWEAVE_BUFFER_DEMO=1` 时只打印 `{"status":"ready"}` 然后 `return 0`，不提供服务 | 演示环境若误用这个开关，草稿箱会「启动成功但什么都不做」——与 `ai4-c61f` 修掉的静默降级是同一类形状 |

`ai4-grlc` 记的那条跨平台缺陷我认为是真的：`Path("C:/absolute").is_absolute()` 在 POSIX 上是 `False`，`parts` 为 `('C:', 'absolute')`，两个条件都不成立，逃逸路径会被静默接受。本机 Windows 上 runtime 106 项全绿，正说明这条只在 Linux 上红——而 Linux 上没人跑。

---

## 五、模块完成度

| 模块 | 完成度 | 依据 | 还缺什么 |
| --- | --- | --- | --- |
| Research Mapping 领域 | **完成** | 124 项默认 + 127 项连真实 TerminusDB 通过；管理 MCP 工具面齐 | 无（对外工具面已发布） |
| LLM-Wiki 领域 | **完成** | 136 项默认 + 148 项连真实存储通过 | 同名测试修复（不影响功能） |
| 中央草稿箱 buffer | **完成** | 28 passed；真实 HTTP 端到端已在 `ai4-roow` 验证 | 无 |
| Registry | **完成** | 14 passed；联系人查询与审计账本已接 | 无 |
| Handoff Coordinator | **完成** | 86 passed；真实 Kafka + 真实 TerminusDB 的端到端 1 passed | 无 |
| email-service | **基本完成** | 114 passed；真实 SMTP 适配器已接 | 一次真实 163 投递（缺授权码，`ai4-ceqq` AC11 诚实挂起） |
| 中央 Agent（centre-agents） | **完成**（worker 子项目是库，不是入口） | 四个角色 69 项通过；passthrough 已改为显式开关，缺 Key 会 fail fast | 无。但要注意：`centre-agents/worker` 的 `main.py` 只做配置校验并打印一行，真实 worker 循环在 `gateway/mcp` 的 `run_worker_process` 与 `subscriber` 的 `SubscriberWorkerRunner` 里 |
| 看板（dashboard-api + web-ui） | **可用，但只接 1/4 来源** | 实跑 `mode=live`、mapping=fresh；wiki/gateway/queue 未配置 | 把三个来源接进 demo-stack |
| 端侧套件（researcher toolkit） | **基本完成** | runtime 106、bridge 35、stdio 1 全绿；三传输齐备 | `ai4-grlc` 四缺陷；跨 harness 实际安装未验 |
| 演示场景（`ai4-aaff`） | **进行中** | 输入快照、T1 检查、T2 本机基线、真实 TerminusDB 治理链路都有证据 | 计时演示、SciencePal 真实承担 T1/T2、驳回分支实演 |
| SciencePal 集成 | **打通 smoke，未打通科研执行** | 真实 run 三次成功（15.8s / 32.2s / 19.2s），产物 sha256 与去重已验证 | 用 SciencePal 跑 Iris 的 T1/T2；报告 → 候选 → 正式化（`ai4-roow`） |
| 生产部署 / 公网访问 | **未开始** | `docs/TECH_STACK.md` 仍列为未确定项 | 赛事要求评审期链接可访问 |

---

## 六、风险清单（按对提交的影响排序）

1. **SciencePal 还未承担核心科研步骤**（`ai4-aaff` 两条 AC 未勾）。赛事明确规定「仅用于撰写文案不算有效使用」。现有 smoke 是 `hello.txt` 级别，评审看的是「谁做了数据分析」，这一条没有替代方案。
2. **没有评审期可访问的链接**。赛事要求「提交的项目、智能体或工作流链接在评审期间必须能够正常访问和演示」，而当前只能在演示者本机 `docker compose` + `scripts/demo-dashboard.ps1` 起。这是资格层面而非评分层面的风险。
3. **CI 从未真正执行**。`.github/workflows/ci.yml` 在 Gitee 不触发，Gitee Go 未接。所有「绿」都是个人机器上的绿，跨平台缺陷只能靠运气发现。
4. **单一人员承载整条交付主线**：`ai4-aaff` / `ai4-jckq` / `ai4-roow` / `ai4-v869` 四张票同一人，且互为上下游。
5. **看板只覆盖 1/4 来源**：演示叙事若强调「平台全景可见」，现场会被 `unavailable` 打断。
6. **验证证据与 HEAD 容易脱节**：`docs/ci.md` 的 785、`ai4-txhf` 历史上的 82，都是同一个模式。
7. **24 张已关闭票验收未勾**：不影响功能，但会让「关闭」这个动作失去证据含义。

---

## 七、距 10 月 31 日的建议（3 天）

### 7.1 先做（半天）

1. **修 CI 汇总 bug 与同名测试**：两处都是十几行内的事，前者影响所有后续判断，后者影响通知失败路径的覆盖。
2. **文档三处对齐**：`docs/ci.md` 数字、`centre-control/README.md` 补三行、把「待用户审阅」的 spec 状态改为「已实现」。
3. **删本地 `sci-weave/task-agent/` 残留**，改掉 `demo-dashboard.ps1` 里 `pwsh` 的提示。
4. **决定 `shared/message-envelope` 的去留**：要么让 coordinator 与 subscriber 真的用它编解码（协议包才有意义），要么在票里写明「先放着、不接」。二选一都行，唯独不能继续「有测试、没调用方」。

### 7.2 打通演示主线（1–1.5 天）

5. **把 demo-stack 的来源补齐**：至少让 `queue`（subscriber 的看板）与 `wiki` 起来，让看板 `partial=false`。这两条服务端都已实现，缺的是 compose 与环境变量。
6. **决定公网暴露方案并从最小形态落地**：一台机器 + `docker compose` + 反代 + HTTPS，够用即可；不必做生产级编排。同时把「评审期可用」写进 `ai4-aaff` 的验收。

### 7.3 赛事硬门槛（与 7.2 并行，最优先）

7. **用 SciencePal 跑一次真正的 Iris T1/T2**：bridge 已有 `start/status/collect` 与上传能力，需要的是把 `check_iris_input.py` / `run_iris_baseline.py` 作为输入装进沙箱跑一遍，把 run_id、产物 sha256、指标回填到 `evidence-card.md` 与 `ai4-aaff`。这一步不依赖任何中央服务。
8. **补一条驳回分支的实演截图/记录**：`run_iris_mapping_pipeline.py` 已能在真实 TerminusDB 上跑批准路径，驳回路径需要一条可观察轨迹。

### 7.4 提交材料

9. 5 页说明（`project-summary.md` 草稿已在，补 SciencePal 实演段）、3–5 分钟视频（`demo-script.md` 已有分镜与计时，实测 260s）、原创性与第三方资源声明（附件 A 已起草）。

### 7.5 明确不做

- 24 张「已关闭但验收未勾」票的集中补勾（只在 `ai4-bp6v` 范围内做）。
- 两套运行时的「共用内核」重构。
- 生产级容器编排、密钥管理、副本与保留期。

---

## 八、附录：复现命令

```powershell
# 全量回归矩阵（本机）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci.ps1

# 连真实 TerminusDB（先起 sci-weave/service/terminusdb/compose.yaml）
$env:SCIWEAVE_RUN_TERMINUSDB_INTEGRATION = "1"
$env:SCIWEAVE_MAPPING_TERMINUSDB_URL  = "http://127.0.0.1:6363"
$env:SCIWEAVE_MAPPING_TERMINUSDB_STORE = "admin"
$env:SCIWEAVE_MAPPING_TERMINUSDB_USERNAME = "admin"
$env:SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD = "<store-key>"
$env:SCIWEAVE_WIKI_TERMINUSDB_URL     = "http://127.0.0.1:6363"
$env:SCIWEAVE_WIKI_TERMINUSDB_DATABASE = "sciweave_review_check"
$env:SCIWEAVE_WIKI_TERMINUSDB_STORE    = "admin"
$env:SCIWEAVE_WIKI_TERMINUSDB_USERNAME = "admin"
$env:SCIWEAVE_WIKI_TERMINUSDB_PASSWORD = "<store-key>"

uv run --directory sci-weave/centre-control/research-map  --with pytest --with pytest-asyncio pytest tests -q
uv run --directory sci-weave/centre-control/research-wiki --with pytest --with pytest-asyncio pytest tests -q

# 协调器端到端（真实 Kafka）
$env:SCIWEAVE_RUN_KAFKA_INTEGRATION = "1"
$env:SCIWEAVE_COORDINATOR_KAFKA_BOOTSTRAP = "127.0.0.1:19092"
uv run --directory sci-weave/centre-control/coordinator --with pytest --with pytest-asyncio pytest tests/test_handoff_e2e.py -q

# 演示看板
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\demo-dashboard.ps1 -ResetSeed
curl http://127.0.0.1:8702/api/dashboard/snapshot
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\demo-dashboard.ps1 -Stop

# 工单索引
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py check
```

> 注：在受 DSH 沙箱限制的环境里跑 pytest 需要把 `TEMP`/`TMP`/`TMPDIR` 指到工作区内可写目录，并把 `UV_CACHE_DIR` 指到工作区，否则 `tempfile.mkdtemp` 建出的目录对受限令牌不可写，会出现大面积 `sqlite3.OperationalError: unable to open database file` 与 `PermissionError` 假失败。本报告的 861 项全绿是在解除该限制后得到的。

---

## 九、本次审查的局限

1. 未验证 Linux/macOS 上的行为；`ai4-grlc` 的跨平台缺陷来自代码推理与 Windows 侧全绿的对照，不是 Linux 实跑。
2. 未做安全渗透：MCP 鉴权、能力档越权、令牌作用域只做了代码阅读与既有测试覆盖的确认。
3. 未跑 `docker compose` 形态的 demo-stack（用的是同源的本机三进程脚本），因此镜像构建链路依赖 `ai4-0uu6` / README 的记载。
4. 未评估 SciencePal 平台侧能力边界；T1/T2 能否由 SciencePal 稳定承载，取决于平台沙箱能否装下这两个脚本。
5. 本次审查未修改任何代码与工单；文中列出的 11 处缺陷未建票，处置方式待确认。
