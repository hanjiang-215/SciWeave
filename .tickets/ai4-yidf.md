---
id: ai4-yidf
status: open
deps: []
links: [ai4-fv1r, ai4-he04, ai4-a2ba, ai4-z3z4, ai4-fm4a, ai4-8dgd, ai4-derq]
created: 2026-10-28T00:57:36Z
type: epic
priority: 1
assignee: Frank Qi
tags: [centre-control, centre-agents, agent, correctness]
---
# 中央 Agent 运行时按 Task Agent 模板补齐：预审从事件到工具调用打通

中央 Agent 的职责只有一件：对 Research Mapping 与 LLM-Wiki 的已存在候选做预审，把结论追加进领域治理日志，必要时生成混合候选。三个组件（处置面、消息监听、短生命周期 Worker）都在仓库里，代码也在，但**这条链上没有一处真正把工具递到模型手里，也没有一处真正把一轮 loop 拉起来**。

三处断链叠在一起：

1. **触发面为零。** `gateway/ingest` 消费到治理事件后，`recompute_triggered` 只是一个计数，打进日志字段就结束了。没有代码写执行记录，没有代码拉起 Worker。中央侧判定「该重算了」，然后什么也没发生。
2. **工具面为零。** `worker` 起 fast-agent 时没有声明任何 MCP server，生成的 `fast-agent.yaml` 只有 `compaction` 与 `session_history` 两行，没有 `mcp.servers`。模型手里一个工具都没有，读不到候选，也写不了预审结论，唯一能做的是照着一句「把负责人的命令简洁地完成」编一段话。
3. **卡片是死的。** `sci-weave/toolkits/centre-agent-toolkit/mcp/` 下六张卡片已按 capability 收窄（含 `list_reviewable_candidates`、`append_prereview_log`、`create_merged_candidate`），但 `centre-agents` 的源码一次都没读过它们；而且 `install.sh` 只拷 `bin cron systemd README.md`，**`mcp/` 和 `suite.yaml` 根本没被装进去**，`check.sh` 也不检查它们。

外加一处稳定性缺陷：`worker_leases` 只有 `acquired_at`，没有过期时间，读取侧只判断「有没有这一行」。一次 Worker 崩溃之后，那个目标就永远拿不到租约。

后果：投给中央 Agent 的候选永远得不到预审结论。`docs/data-flow/centre-agent.md` 里那条「事件触发 → 拉全量快照 → 追加预审日志」，目前只有中间一段。

规格见 [`docs/superpowers/specs/2026-10-28-centre-agent-runtime-template-port-design.md`](../../docs/superpowers/specs/2026-10-28-centre-agent-runtime-template-port-design.md)。

## 几个已定的判断

- **搬接缝，不搬运行时包。** 按 [ADR-0002](../../docs/adr/0002-work-agent-two-codebases.md)，两侧源码分开、不 path 依赖，中央侧自己实现加载层。ADR-0002 的前提（「Agent 定义、MCP 卡片只有套件需要」）在这里确实松动了，但推翻它需要单独的裁决，不在本票里夹带。已记录为已知债务。
- **触发是快照审，不是按节点审。** 中央侧的目标是一次全量候选快照，执行标识用（域，事件，去抖窗口），不用单个 `candidate_id`。
- **状态机不缩窄。** 中央侧保持 9 态。套件侧只有 6 态是研究员侧处置面的有意裁剪；要对齐是套件向中央靠，不是反过来。

## Acceptance Criteria

- [ ] 一次治理事件能端到端产出一条执行记录、拉起一个真实 Worker 子进程，并在处置面上看到它的状态
- [ ] 生成的 fast-agent 配置里含 `mcp.servers`，且缺必填环境变量时硬失败并指出变量名
- [ ] Worker 的预审指令、模型与允许资源来自一份 YAML 定义，不再硬编码
- [ ] Worker 租约带过期时间，崩溃后不需要手工删库即可重新派发
- [ ] 套件安装后卡片目录与套件清单真的在目标目录里，`check.sh` 覆盖它们
- [ ] 每一项都有对应垂直切片票，且各自的验收可独立验证

## Notes

**2026-10-28T00:57:36Z**

六张切片票已建。依赖链的骨架是「租约 → 派发」这条主干，`ai4-1aeg` 与 `ai4-e959` 是所有下游的前置；到 `ai4-e959` 之后分两路并行：

| 票 | 交付什么 | 阻塞于 |
| --- | --- | --- |
| `ai4-1aeg` | 租约写入过期时间，崩溃后不必手工删库 | 无（可立即开始） |
| `ai4-e959` | Worker 以独立子进程派发，派发方只传执行标识 | `ai4-1aeg` |
| `ai4-qula` | 治理事件落成执行记录并派发，标识按快照审 | `ai4-1aeg`、`ai4-e959` |
| `ai4-tesq` | 注入 `mcp.servers`，模型第一次拿到工具 | `ai4-1aeg`、`ai4-e959` |
| `ai4-k2le` | 预审 Agent 定义从 YAML 加载 | `ai4-tesq` |
| `ai4-8d9j` | 安装脚本补齐 `mcp/` 与 `suite.yaml`，自检覆盖 | 无（可立即开始，与主线并行） |

`ai4-qula` 与 `ai4-tesq` 刻意互不阻塞：前者解决「谁拉起一轮」，后者解决「拉起之后模型手里有什么」，两条独立验证，合起来才通。`ai4-8d9j` 独立，因为它的消费者在套件一侧，且在 `ai4-tesq` 把卡片目录指过来之前就已经是个真实缺陷。

本机没有 `DEEPSEEK_API_KEY`，也没有领域 MCP 令牌，因此「模型真的调用工具并产出预审报告」这一步无法在本机验证。交付物是「接缝接上且被测试钉住」，不是「预审可用」。任何一张票都不得用测试通过冒充真机可用。
