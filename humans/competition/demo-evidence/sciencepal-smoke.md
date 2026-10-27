# SciencePal 真实执行 smoke（2026-10-27）

> 目的：在接入外部 harness（WorkBuddy / DSH / 其他 Agent）前，先证明 bridge 能真实发起 SciencePal run、读到终态、收到产物。
> 令牌只从本机 `.env` 读取，本文不记录令牌值。

## 环境

- bridge：`sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/custom-mcp/sciencepal-bridge`
- 端点：`https://sciencepal.ai/api`
- 本机时间：2026-10-27（Asia/Shanghai）
- `agents.list` 返回空数组：该账号没有自定义 Agent；不影响发起 run（默认/auto 选择仍可用）。

## 结果

| 项 | 结果 |
| --- | --- |
| 最小 run（纯文本） | `run_id=670a5341-1223-49af-8863-495748135e73`，15.8s 完成，无产物 |
| 带输入文件的 run | `run_id=2772f7b7-c5eb-4207-b8a5-574d7bb11815`，32.2s 完成 |
| CLI start/status | `run_id=d06aff3b-9ea0-42d9-b37f-715508e89617`，19.2s 完成，单行 JSON |
| CLI collect | 对 `2772f7b7…` 收 `hello.txt`，sha256 `565339bc…2bb3`，镜像重复被跳过 |
| 上传文件落点 | `/workspace/probe_input.txt`（sha256 `c412fc93…c039`） |
| 产物目录 | `/outputs` 与 `/workspace/outputs` 是同一份产物的两个视图 |
| 产物 | `hello.txt`（2B，`565339bc…2bb3`）、`probe.txt`（456B，`8da941dd…7273`） |
| 去重 | 两个根各出现一次，`collect` 按 `(name, sha256)` 只保留一份 |
| 排队 | 第一个 run 立即开始；第二个 run 排队约 2.5 分钟后才 `running` |
| 无 token | `sciencepal_token_missing` |
| 错误 token | `sciencepal_unauthorized` |
| HTTP MCP | `initialize` 200；`tools/list` 返回 5 个工具；`serverInfo.name=sciencepal-bridge` |

## 沙箱布局（实测）

```text
/
├── app, bin, etc, usr ...        # 系统目录，不收集
├── outputs/                      # 产物
├── workspace/
│   ├── probe_input.txt           # initiate 上传的文件落在这里
│   ├── outputs/                  # 与 /outputs 同一份产物
│   ├── skills/                   # SciencePal 自带技能库，很大，必须跳过
│   ├── memory/                   # 运行时记忆，跳过
│   └── _refs/                    # 引用缓存，跳过
```

第一次 `collect` 从 `/` 全盘扫描，进入 `workspace/skills/ppt-master/...`，在 Windows 上触发 `WinError 206 文件名或扩展名太长`。已改为只收 `/outputs` 与 `/workspace/outputs`，并跳过 `skills/`、`memory/`、`_refs/`。

## 对集成的结论

1. **可用**：SDK 的 HTTP 面足以完成“上传 → 发起 → 轮询 → 下载”，不依赖公网 MCP。
2. **排队不可忽略**：演示要提前发起，或预留至少 3 分钟；不要假设 run 秒级开始。
3. **产物按目录收**：以 `/outputs` 为准；上传输入在 `/workspace` 根，不应混入产物。
4. **列表为空是正常**：`agents` 为空时仍可发起；领域 Agent 的选择交给默认/auto，并在报告里记录。
5. **失败可判**：401 与 token 缺失有稳定错误码；下一步补 run failed / 超时的真实样本。

## 复现命令

```bash
cd sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/custom-mcp/sciencepal-bridge
uv run --env-file .env python scripts/smoke.py --list-agents
uv run --env-file .env python scripts/smoke.py --prompt "Reply with exactly: OK" --timeout 240
```
