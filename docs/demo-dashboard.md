# 看板真实数据运行手册

把 Web 看板从内置 fixture 快照切到**真实** Research Mapping 数据，一条命令起三个进程。

## 为什么需要它

`sci-weave/centre-control/web-ui/src/App.vue` 在 `VITE_DASHBOARD_API_URL` 为空时使用 `fixtureQuery`，页面顶部会显示「演示数据模式 / 不代表真实服务状态」的橙色横幅。`dashboard-api` 的四个来源槽（mapping / wiki / gateway / queue）也只有配了 URL 才会去取数。

也就是说：**看板默认是空的**，要看到真实数据，必须有人把「领域看板来源 → dashboard-api → 前端」这三段接起来。本手册就是这条链路的启动方式。

## 三层结构与数据流

```
research-map (真实 TerminusDB + SQLite)
   └─ GET /api/dashboard/source/mapping      ← 正式路线投影（项目、任务、依赖、事件）
        ↓ 由 dashboard-api 拉取
gateway/subscriber （可选，见 ai4-nvuj）
   └─ GET /api/dashboard/source/queue        ← 消息监听状态、消费组与最近队列事件
        ↓ 由 dashboard-api 拉取
dashboard-api
   └─ GET /api/dashboard/snapshot            ← 多来源聚合，单个来源失败降级为 unavailable
        ↓ 由前端拉取（跨域，需 CORS）
web-ui (Vite dev server)
   └─ 页面渲染 mode: live
```

`queue` 来源默认不启（需要先有一个 subscriber 存储），配了 `SCIWEAVE_DASHBOARD_SOURCE_QUEUE_URL` 才会接入；没配时看板的「消息监听」区显示不可用，属预期。

## 前置条件

| 依赖 | 检查方式 |
| --- | --- |
| 本机 TerminusDB | `docker compose -f sci-weave/service/terminusdb/compose.yaml up -d`，默认 `http://127.0.0.1:6363` |
| research-map 依赖 | 在 `sci-weave/centre-control/research-map` 执行过 `uv sync --locked` |
| dashboard-api 依赖 | 在 `sci-weave/centre-control/dashboard-api` 执行过 `uv sync --locked` |
| 前端依赖 | 在 `sci-weave/centre-control/web-ui` 执行过 `npm install` |

脚本会自己检查 TerminusDB 可达、三个依赖路径存在，缺任何一项都会直接报错退出。

## 用法

```powershell
# 启动（Windows PowerShell）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\demo-dashboard.ps1

# 停止
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\demo-dashboard.ps1 -Stop

# 重建演示域（丢了 SQLite 或想重置数据时）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\demo-dashboard.ps1 -ResetSeed
```

```bash
# Linux / macOS（尚未在非 Windows 主机验证，首次使用请记录结果到 ai4-c22u）
scripts/demo-dashboard.sh
scripts/demo-dashboard.sh --stop
scripts/demo-dashboard.sh --reset-seed
```

成功时输出：

```
模式      : live
mapping   : fresh
项目/任务 : 1 / 3
部分来源  : True

看板地址  : http://127.0.0.1:5173
```

浏览器打开看板地址即可。`部分来源: True` 是正常的——脚本只接上 mapping 来源，wiki / gateway / queue 仍为空。要补 queue，先起 subscriber 的看板端点（见下文配置表）再把 URL 传给 dashboard-api。

## 演示数据从哪来

`scripts/seed_dashboard_demo.py` 在**持久**的 TerminusDB 库和 SQLite 上建最小真实状态：

1. 建 `sciweave_dashboard_demo` 库并写入 `TaskNode` / `DependencyEdge` schema；
2. 种入正式路线 `T1 → T2 → T3`（两条依赖边），状态为 `succeeded / succeeded / waiting`；
3. 把这次提交的 commit hash 记成 SQLite 里的当前正式版本。

脚本幂等：已有当前正式版本就直接返回 `already_seeded`，`--reset` 才重建。

它与 `humans/competition/demo-evidence/run_iris_mapping_pipeline.py` 的区别是刻意的——那份是**赛事证据包**，必须在临时库上一次性跑完并清理；本脚本是**开发态种子**，要留下可反复查看的数据。

## 配置

全部经环境变量，脚本只提供开发默认值。要改端口就设环境变量再运行。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SCIWEAVE_MAPPING_DASHBOARD_HOST` / `_PORT` | `127.0.0.1` / `8701` | mapping 看板来源监听地址 |
| `SCIWEAVE_DASHBOARD_HOST` / `_PORT` | `127.0.0.1` / `8702` | dashboard-api 监听地址 |
| `VITE_DEV_HOST` / `VITE_DEV_PORT` | `127.0.0.1` / `5173` | 前端 dev server |
| `SCIWEAVE_MAPPING_TERMINUSDB_URL` | `http://127.0.0.1:6363` | TerminusDB 地址 |
| `SCIWEAVE_MAPPING_TERMINUSDB_STORE` / `_DATABASE` | `admin` / `sciweave_dashboard_demo` | 库位置 |
| `SCIWEAVE_MAPPING_TERMINUSDB_USERNAME` / `_PASSWORD` | `admin` / `root` | 本机固定容器的默认凭据 |
| `SCIWEAVE_MAPPING_DOMAIN_ID` | `iris-demo` | 看板展示的映射域 |
| `SCIWEAVE_MAPPING_SQLITE_PATH` | `research-map/data/dashboard.sqlite` | 治理记录库 |
| `SCIWEAVE_SUBSCRIBER_DASHBOARD_PORT` | 未设 | subscriber 看板端点监听端口；不设就不起 |
| `SCIWEAVE_SUBSCRIBER_DASHBOARD_HOST` / `_TOKEN` | `127.0.0.1` / 空 | 监听地址与 Bearer 令牌（设了令牌则必须带 `Authorization`） |
| `SCIWEAVE_DASHBOARD_SOURCE_QUEUE_URL` | 未设 | 指向 subscriber 的 `/sources`（或 `/api/dashboard/source/queue`），不设则 queue 槽为 unavailable |

`SCIWEAVE_DASHBOARD_CORS_ORIGIN` 由脚本从前端端口推导，不需要手工配——手工配错会让浏览器拿不到数据。

## 常见问题

**脚本报「无法加载，文件未数字签名」**  
本机 PowerShell 执行策略限制。用 `powershell -NoProfile -ExecutionPolicy Bypass -File ...` 调用，或对当前用户放开：`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`。

**看板显示「演示数据模式」**  
前端没拿到 `VITE_DASHBOARD_API_URL`。这个变量在**启动时**注入，改完要重启 dev server。

**`mapping: unavailable`**  
两个可能：TerminusDB 里没有该库，或 SQLite 里没有当前正式版本。跑 `-ResetSeed` 重建；仍失败就看 `research-map` 进程的报错。

**端口被占**  
脚本启动前会先清理自己上一轮留下的进程；若仍被占，说明是别的程序，换端口（设环境变量）而不是杀进程。

## 相关工单

- `ai4-c22u`：本脚本
- `ai4-nvuj`：queue 来源（补齐后 `部分来源` 才会只剩 wiki / gateway）
- `ai4-0uu6`：容器编排（把这条链路搬进 compose）
