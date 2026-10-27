# 跨 harness 接入

协作者 Agent 不绑定 SciWeave 自带的 runtime。任何能执行 shell 或连接 MCP 的 harness（WorkBuddy、DSH、Claude Code、其他集成 Agent）都可以安装这套能力；SciWeave 只保留地图、草稿与治理。

## 三种调用方式

按 harness 能力从高到低选：

| 方式 | 适用 | 入口 |
| --- | --- | --- |
| MCP stdio | 支持 stdio MCP 的 harness | `uv run --project <bridge-dir> python src/main.py` |
| MCP HTTP | 只连 HTTP MCP 的 harness | `python src/main.py --transport http --host 127.0.0.1 --port 8791`，URL `http://127.0.0.1:8791/mcp` |
| CLI | 任何能执行 shell 的 harness | `bin/sciencepal.cmd`（Windows）或 `bin/sciencepal.sh`（Linux/macOS） |

CLI 输出固定为一行 JSON，退出码：`0` 成功，`1` 配置错误，`2` SciencePal 业务错误。

## 安装步骤

1. 安装依赖并配置 token：

   ```bash
   cd <bridge-dir>
   uv sync
   # 编辑 <bridge-dir>/.env，填入 SCIENCEPAL_ACCESS_TOKEN
   ```

2. 把 `deploy-task-agent-skills/sciencepal-research/` 复制进 harness 的 skills 目录。不同 harness 的目录不同，以它自己的约定为准。

3. 选一种调用方式：
   - **MCP**：把 `harness/generic-mcp.json` 的 `<bridge-dir>` 换成实际路径后注册；
   - **CLI**：让 harness 直接执行 `bin/sciencepal.cmd` / `bin/sciencepal.sh`。

4. 冒烟：

   ```bash
   bin/sciencepal.cmd agents
   bin/sciencepal.cmd start --instruction "Reply with exactly: OK" --idempotency-key smoke:1
   ```

## Harness 对照

| Harness | Skill | CLI | MCP | 备注 |
| --- | --- | --- | --- | --- |
| WorkBuddy | 复制 skill 目录 | `bin/sciencepal.cmd` / `.sh` | 若版本支持 stdio MCP，用 generic 配置 | 以 WorkBuddy 当前版本的 skills/MCP 配置为准 |
| DSH | 复制 skill 目录 | `bin/sciencepal.cmd` / `.sh` | 若版本支持 MCP，用 stdio 或 HTTP | CLI 是保底，不依赖 MCP |
| Claude Code | 复制 skill 目录 | `bin/sciencepal.cmd` / `.sh` | `.mcp.json`（generic 同构） | — |
| 其他集成 Agent | 把 `SKILL.md` 正文放进系统提示词即可 | 有 shell 就用 | 有 MCP 就用 | 两者都没有时，报告 `sciencepal_harness_unsupported` |

## MCP 配置示例

`harness/generic-mcp.json`：

```json
{
  "mcpServers": {
    "sciencepal": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "<bridge-dir>",
        "--env-file",
        "<bridge-dir>/.env",
        "python",
        "src/main.py"
      ],
      "cwd": "<bridge-dir>"
    }
  }
}
```

`cwd` 必填：`.env` 里的相对路径按进程工作目录解析；不同 harness 的启动目录不同。

HTTP 方式：

```bash
cd <bridge-dir>
uv run --env-file .env python src/main.py --transport http --host 127.0.0.1 --port 8791
```

HTTP 模式没有远程鉴权，只绑回环地址；需要跨机访问时前面加带认证的反向代理，不要直接暴露公网。

## 任务与结果怎么交接

1. **任务进**：SciWeave 侧导出 `task-packet.json`（含固定 `formal_revision_id`、节点目标、验收条件、输入文件与 sha256）。harness 把它作为 prompt 的一部分，输入文件放到 bridge 工作区或通过 `--file` 上传。
2. **科研执行**：harness 调 `sciencepal_start`（MCP）或 `sciencepal start`（CLI）。
3. **结果出**：harness 调 `collect`，拿到产物与 sha256；按 Skill 的 `ExecutionReport` 结构写 `execution-report.json`。
4. **回写**：若 harness 支持 `draft-buffer` MCP，直接 `create_draft`；否则把 `execution-report.json` 交给 SciWeave 侧导入（见 `ai4-` 的“执行报告回写地图”票）。

协作者不要直接改正式图；报告只是草稿，候选与正式化仍由人完成。
