# SciencePal 最小能力验证（对接材料）

> 关联工单：`ai4-v869`（SciencePal 承载执行面与中央服务 MCP 对接：方案、风险与解决预案）、`ai4-aaff`（默认科研示例场景与验证证据）。
>
> 状态：**等待 SciencePal 平台环境**。本目录是 v869 预案第 8 步的"最小能力验证"材料——用户注册/登录 SciencePal 并进入可创建项目的沙箱后，按本 README 的清单逐项执行，每项产出即决定路径 A 或 B。

## 验证目标（从 v869 转载）

SciencePal 沙箱需要同时满足三项，才能承接 T1 数据检查 / T2 分析执行：

1. **脚本执行**：能在沙箱内运行 Python 脚本（T1/T2 均只用标准库，参数固定）。
2. **沙箱出站**：沙箱能访问中央管理 MCP 的公网/隧道端点（路径 A/B 都依赖这条）。
3. **原生 MCP 配置**：能配置外部 MCP server（路径 A）；若不能，走路径 B（把 MCP JSON-RPC 调用封装成 skill）。

> 时间风险提示：SciencePal 平台闭源、官网内容需登录、GitHub 同名仓库为无关占位。注册后应**当天**跑三项最小验证，给后续回填执行记录留 ≥2 天缓冲。

## 执行清单

### 第 0 步：准备本地证据（无需 SciencePal，已完成）

- 固定脚本：`humans/competition/demo-evidence/check_iris_input.py`、`run_iris_baseline.py`（仅标准库，参数固定 K=3 / 种子 20261023 / 70/30）。
- 固定输入：`demo-evidence/iris_data.csv`（SHA-256 `ea110d42...b6f9f4`，行尾归一化）；失败注入副本 `iris_data_failure_inject.csv`。
- 本机对照结果：`iris_input_check.json`、`iris_baseline_result.json`（Sandbox 结果不一致时以沙箱实际输出为准并回填）。

### 第 1 步：最小测试 skill

在 SciencePal 项目中加载本目录 `skills/minimal-probe/SKILL.md`（或按平台格式复制其内容）。该 skill 做三件小事：

1. 打印 `Hello from SciWeave probe`；
2. 运行 `python check_iris_input.py iris_data.csv`（脚本与数据一并上传到沙箱的同一目录，来源见第 0 步）；
3. 对中央端点发一次 HTTP GET（出站探测，见第 2 步）。

> 如果平台不支持 skill 目录格式，直接把 SKILL.md 正文拷进 agent 系统提示词。

### 第 2 步：沙箱出站探测

中央管理 MCP 就绪后（见 `docs/deploy-central-mcp.md`），在沙箱测三项：

```bash
# 1) 无鉴权的健康端点（不断言业务，只验证出站可达）
curl -sS -m 10 https://<central-host>/health

# 2) 带 Bearer 的 MCP initialize（验证端点 + 令牌 + JSON-RPC 通道）
curl -sS -m 10 -X POST https://<central-host>/mcp \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"sciencepal-probe","version":"0.1.0"}}}'

# 3) 只读工具探测
curl -sS -m 10 -X POST https://<central-host>/mcp \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

判定：

- 三项都通 → 路径 A 可行（原生/自定义 MCP server 配置或 skill 内嵌 HTTP）。
- 第 1 项通、第 3 项不通 → 只允许出站但限制非 GET 方法？重测做 POST；仍不通则中央侧只读不可用，回查 `docs/deploy-central-mcp.md` 的端点解释。
- 第 1 项不通 → 沙箱无出站，SciencePal 无法对接中央治理面；记录并按 v869 预案第 8 条走兜底（本机真实治理链路 + Replay 链接 + 录屏，如实标注不满足硬门槛）。

### 第 3 步：路径判定

| 观测 | 结论 |
| --- | --- |
| 平台支持配置外部 MCP server（原生工具面） | 路径 A：直接挂中央端点，agent 原生看到 `get_formal_mapping` / `submit_candidate` / `preview_candidate` |
| 平台不支持原生 MCP，但出站 GET/POST 可用 | 路径 B：把 MCP JSON-RPC client 封装成 skill（`skills/mcp-bridge/SKILL.md` 提供模板），agent 经 skill 调中央端点 |
| 出站不可用 | 兜底，见上 |

### 第 4 步：回写

- 把第 1–3 步的实际输出（截图/文本/Replay 链接）追加到 `humans/competition/demo-evidence/evidence-card.md` 的「待 SciencePal 补的交割物」。
- 更新 `demo-script.md` 的实际计时列。
- 回写 `ai4-v869` Notes 更新验收勾选；复核 `ai4-aaff` 两条 SciencePal 验收项。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `skills/minimal-probe/SKILL.md` | 最小测试 skill：打印 + T1 检查 + 出站探测 |
| `skills/mcp-bridge/SKILL.md` | 路径 B 的 MCP JSON-RPC 桥 skill 模板 |
| `agent/t2-baseline-agent.md` | T2 执行 agent 的任务指令模板（与中央开放面对齐） |
| `docs/deploy-central-mcp.md` | 中央管理 MCP 公网可达性检查与启停说明 |

T1/T2 脚本与 Iris 数据不在本目录，统一从 `humans/competition/demo-evidence/` 取用（`check_iris_input.py`、`run_iris_baseline.py`、`iris_data.csv`、`iris_data_failure_inject.csv`）。上传沙箱时把这几个文件放在同一目录，命令即 `python check_iris_input.py iris_data.csv`。此前本目录下的 `checks/` 是逐字节副本，两份曾因改动不同步而产生「本机通过、沙箱失败」的风险，已移除（`ai4-3vkc`）。
