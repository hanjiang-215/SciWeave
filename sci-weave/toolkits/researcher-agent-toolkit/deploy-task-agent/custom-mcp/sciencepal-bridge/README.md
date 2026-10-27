# sciencepal-bridge

研究员端的 SciencePal 执行桥：把一次科研任务交给 SciencePal 的领域 Agent 与沙箱，收齐产物、算好哈希，再把证据交给协作者写报告。

边界：

- 只调 SciencePal，不写 Research Mapping 正式图。
- 只开草稿：`report --write-draft` 写的是中央草稿箱的 `mapping_change` 草稿（`namespace=mapping`）。不提交候选、不正式化——那两步分别留给人和 Project Owner。
- 令牌只从环境变量读取；日志、错误和返回体都不含令牌。
- 只允许上传 `SCIENCEPAL_WORKSPACE` 下的文件；下载也落在这个目录。

## 安装与配置

```bash
cd sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/custom-mcp/sciencepal-bridge
uv sync
```

把 SciencePal 控制台生成的 access token 填进本目录的 `.env`（已 gitignore）：

```dotenv
SCIENCEPAL_ACCESS_TOKEN=eyJ...
SCIENCEPAL_BASE_URL=https://sciencepal.ai/api
SCIENCEPAL_WORKSPACE=
```

## 最小验证

```bash
# 只列当前 token 可见的 SciencePal Agent
uv run --env-file .env python scripts/smoke.py --list-agents

# 真跑一个小任务并下载产物
uv run --env-file .env python scripts/smoke.py --prompt "用一句话说明你能做什么" --download
```

先确认四件事，再依赖 `collect` 的过滤规则：

1. 沙箱产物落在哪个目录；
2. 一个 T1/T2 任务的典型时长；
3. 失败 run 的 `status` / `error` 形态；
4. 沙箱根目录里哪些是系统文件。

## 跨 harness

协作者 Agent 可以运行在 WorkBuddy、DSH 或其他集成 Agent 里，不要求 SciWeave runtime。完整矩阵见 [`harness/README.md`](harness/README.md)。

CLI（任何有 shell 的 harness）：

```bash
bin/sciencepal.cmd agents          # Windows
bin/sciencepal.sh agents           # Linux/macOS
bin/sciencepal.cmd start --instruction-file task.txt --idempotency-key exec:123
bin/sciencepal.cmd status <run_id>
bin/sciencepal.cmd collect <run_id>
```

MCP 两种传输：

```bash
# stdio（推荐）
uv run --env-file .env python src/main.py

# 本地 HTTP（只绑回环，无远程鉴权）
uv run --env-file .env python src/main.py --transport http --host 127.0.0.1 --port 8791
# URL: http://127.0.0.1:8791/mcp
```

## MCP 工具

以 stdio 启动：

```bash
uv run --env-file .env python src/main.py
```

| 工具 | 用途 | 关键参数 |
| --- | --- | --- |
| `sciencepal_start` | 发起一次 run，立即返回 `run_id` / `thread_id` | `instruction`、`idempotency_key`、`files_json`、`agent_id` |
| `sciencepal_status` | 查状态；`completed` / `failed` / `stopped` 为终态 | `run_id` |
| `sciencepal_collect` | 下载全部产物、校验 sha256、写 `manifest.json` | `run_id`、可选 `names_json` |
| `sciencepal_cancel` | 停止未终结的 run，幂等 | `run_id` |
| `sciencepal_agents` | 列出可见的领域 Agent | — |
| `sciencepal_report` | 从台账与产物组装 ExecutionReport；`write_draft=true` 时写 `mapping_change` 草稿 | `run_id`、`task_node_id`、`write_draft`、`acceptance_json`、`route_change_json` |

## 执行报告回写（ai4-roow）

外部 harness 跑完一次 SciencePal 执行后，用 `report` 把结果变成一条可审的 ExecutionReport，再决定是否开草稿：

```bash
# 只组装报告，不写任何中央服务
bin/sciencepal.cmd report <run_id> --task-node-id task:t1 --execution-id exec-123 \
  --summary "T1 输入检查通过" --acceptance "150 行、4 特征列=true"

# 组装并写入中央草稿箱，拿回 draft_id
bin/sciencepal.cmd report <run_id> --task-node-id task:t1 --execution-id exec-123 \
  --summary "T1 输入检查通过" --acceptance "150 行、4 特征列=true" \
  --route-change-file route-change.json --write-draft
```

报告契约：`task_node_id`、`execution_id`、`status`、`sciencepal.run_id`、`inputs`/`artifacts` 的 `sha256`、逐条 `acceptance`、`route_change`、`limitations`。两条硬规则：

1. `status=completed` 必须有 `run_id` 且至少一个产物带 `sha256`，否则拒绝组装——空证据不许冒充完成。
2. 失败或停止的报告保留 `run_id`，产物可以为空。

草稿负载是 `{report, proposed_change_set}`，`kind=mapping_change`（沿用草稿箱既有白名单，不新增 kind）。结果里带审计关联字段：`execution_id`、`run_id`、`draft_id`；`candidate_id` 与 `formal_revision_id` 由后续候选与正式化阶段回填。

### L0 与 L1 的边界

- **L0（正式图）**只在 Project Owner 正式化候选时变化。bridge 不碰它，草稿箱也不碰它。
- **L1（候选）**带进度快照；候选由人提交，`candidate_submit` 不下放给 harness token。
- **L2（运行投影）**另立服务，不在本桥范围内。**运行状态（queued/running/…）永远不写进 TaskNode 版本对象**，只作为投影存在。

权限：harness token 只开读与开草稿；候选提交留给人或 Project Owner，正式化永不下放。草稿箱的 `read_draft` / `review_draft` 要求调用方是被评审命名空间的评审人，所以 harness 自己开完草稿读不回来——读回与一审交给 TaskNode Owner 的评审身份做。

`files_json` 形如：

```json
[{"name": "iris_data.csv", "path": "inputs/iris_data.csv"}]
```

相对路径按 `SCIENCEPAL_WORKSPACE` 解析；绝对路径必须落在该目录内。

## 测试

```bash
uv run python -m unittest discover -s tests -v
```

测试使用假 SciencePal 客户端，不需要 token，也不访问网络。

## 已知限制

- 官方 SDK（`sciencepal-sdk==0.1.1`）没有发布到 PyPI，官方 Skills 包以 whl 分发。本服务直接对齐 SDK 的 HTTP 端点，避免在套件里手工装 whl；升级 SDK 时需要同步这里的端点与字段。
- SciencePal 没有 webhook；`status` 是单次查询，轮询节奏由协作者决定。
- 令牌是账号级的，一个 token 能建 run、读写沙箱、管理 Agent；不要放进仓库、日志或演示材料。
- `collect` 默认只收 `/outputs` 与 `/workspace/outputs`；实测两者是同一份产物，按 `(name, sha256)` 去重。上传的输入文件落在 `/workspace` 根目录，不会被当作产物。
- 沙箱的 `/workspace` 还包含 SciencePal 自己的 `skills/`、`memory/`、`_refs/`；这些目录已被跳过，不要改成全盘扫描。
