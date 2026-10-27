---
id: ai4-c22u
status: closed
deps: []
links: []
created: 2026-10-27T03:01:25Z
type: task
priority: 1
assignee: hanjiang
tags: [dashboard, demo, dev-tooling]
---
# 看板真实数据一键启动脚本

提供一条命令把 mapping 看板来源、dashboard-api、web-ui 三个进程拉起，使 Web 看板从 fixture 演示数据切到真实快照。当前 web-ui 在 apiUrl 为空时走 fixtureQuery，页面显示演示数据横幅；dashboard-api 的四个来源槽只有配置了 URL 才生效。缺的是一条可复现的启动编排与自检。

## Design

新增 scripts/demo-dashboard.ps1 与 scripts/demo-dashboard.sh：读取 .env.dashboard（本地、不提交）或环境变量，依次启动 research-map 的 dashboard source（SCIWEAVE_MAPPING_DASHBOARD_MODE=1）、dashboard-api、web-ui dev server，轮询各自健康端点直到就绪，然后打印看板 URL。脚本必须幂等：已在监听的端口不再重复启动，退出时清理子进程。不引入新运行时依赖。

## Acceptance Criteria

1) 一条命令后 GET dashboard-api /api/snapshot 返回 mode=live 且 mapping 来源 status=fresh；2) 脚本可重复执行不产生重复进程；3) Ctrl+C 或参数 -Stop 能清理全部子进程；4) 脚本不写死端口，端口经环境变量配置；5) README 记录命令、前置条件与停止方式；6) 实跑一次并在票内记录命令与输出摘要。

## Notes

**2026-10-27 交付（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`，三者一致。

新增文件：

- `scripts/seed_dashboard_demo.py`：在**持久** TerminusDB 库与 SQLite 上建最小真实状态——`TaskNode`/`DependencyEdge` schema、正式路线 `T1 → T2 → T3`（`succeeded`/`succeeded`/`waiting`，两条依赖边）、SQLite 记录当前正式版本并指向该 commit。幂等：已有当前版本直接返回 `already_seeded`，`--reset` 才重建。刻意与 `humans/competition/demo-evidence/run_iris_mapping_pipeline.py` 区分：后者是赛事证据包，必须用临时库一次性跑完并清理；本脚本是开发态种子，数据要留下。
- `scripts/demo-dashboard.ps1`：启动 mapping 看板来源、dashboard-api、web-ui 三个进程，逐个轮询 `/health` 直到就绪，写 `.demo-dashboard.json` 记录 PID，`-Stop` 按进程树清理。
- `scripts/demo-dashboard.sh`：同逻辑的 shell 版本。
- `docs/demo-dashboard.md`：运行手册（前置条件、命令、配置表、常见问题）。

实测（本机 Windows，TerminusDB 12.0.8 在 `127.0.0.1:6363`）：

```text
模式      : live
mapping   : fresh
项目/任务 : 1 / 3
部分来源  : True
```

三条关键验收逐项验证：

1. `GET http://127.0.0.1:8702/api/dashboard/snapshot` 返回 `mode=live`，`sources` 中 `mapping` 为 `fresh`，`tasks` 3 条、`projects` 1 条。
2. 连续执行两次：第二次先打印三条「已停止 …」，再重新就绪；`Get-NetTCPConnection` 显示 8701/8702/5173 **每端口恰好 1 个监听者**。
3. `-Stop` 后三个端口全部释放，`.demo-dashboard.json` 被删除。

实现中修掉两个真实缺陷，记录备查：

- **状态文件读回为空**：初版把 PID 数组直接 `ConvertTo-Json` 写成顶层数组，读回时 `$state.processes` 是 `null`，清理循环整段跳过、进程残留。改为写入 `{"processes": [...]}` 对象。
- **杀不掉真实进程**：uv 创建的 venv 里 `python.exe` 是启动器，真实解释器是它的子进程，`Stop-Process` 只杀启动器。改为 `taskkill /T` 按进程树杀，并按记录端口兜底清理。

未验证项（如实记录，不当作通过）：

- `scripts/demo-dashboard.sh` 只在 Windows 主机上按 PowerShell 版本验证过，**没有在 Linux/macOS 实跑**。首次在非 Windows 主机使用需补测。
- 前端只验证到 dev server 返回 200、页面含 `#app` 容器、CORS 头正确；**没有在真实浏览器里目视确认渲染结果**。
- `部分来源: True` 属预期：只有 mapping 来源接通，wiki / gateway / queue 仍空；queue 段由 `ai4-nvuj` 处理。


