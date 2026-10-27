# Harness 接入

这套 Skill 不绑定某个 Agent 运行时。三种调用方式按能力从高到低：

| 方式 | 适用 | 入口 |
| --- | --- | --- |
| MCP stdio | 支持 stdio MCP | `uv run --project <bridge-dir> python src/main.py` |
| MCP HTTP | 只连 HTTP MCP | `python src/main.py --transport http --host 127.0.0.1 --port 8791`，URL `http://127.0.0.1:8791/mcp` |
| CLI | 能执行 shell | `bin/sciencepal.cmd` / `bin/sciencepal.sh` |

## 安装

1. 在 bridge 目录执行 `uv sync`，把 token 填进 `.env`。
2. 把本 Skill 目录复制到 harness 的 skills 目录（目录约定由 harness 决定）。
3. 选 MCP 或 CLI：
   - MCP：用 `harness/generic-mcp.json`，把 `<bridge-dir>` 换成实际路径，保留 `cwd`；
   - CLI：直接调用 `bin/sciencepal.cmd` / `bin/sciencepal.sh`。
4. 冒烟：`bin/sciencepal.cmd agents`，再发一个最小 run。

## CLI 形状

```bash
sciencepal agents
sciencepal start --instruction-file task.txt --idempotency-key exec:123 --file inputs/iris.csv
sciencepal status <run_id>
sciencepal collect <run_id> [--name result.json] [--root /outputs]
sciencepal cancel <run_id>
```

每个命令输出一行 JSON；成功退出码 0，配置错误 1，SciencePal 业务错误 2。

## 任务与结果

- 任务进：`task-packet.json` 作为 prompt 的一部分；输入文件通过 `--file` 上传。
- 结果出：`collect` 返回产物与 sha256；按主 Skill 的 `ExecutionReport` 结构写 `execution-report.json`。
- 回写：harness 支持 `draft-buffer` MCP 就直接 `create_draft`；否则交给 SciWeave 侧导入。

WorkBuddy、DSH、Claude Code 的具体配置路径以各自版本文档为准；CLI 是共同保底，不依赖 MCP。
