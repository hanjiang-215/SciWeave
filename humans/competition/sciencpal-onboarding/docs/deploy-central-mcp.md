# 中央管理 MCP 公网可达性检查与启停说明

> 关联：`ai4-v869` 预案第 2 条（公网可达性）。评审期 SciencePal 沙箱必须能访问中央管理端点；内网/本机地址不可达则现场演示失败。

## 目标

让 `research-map` 管理 MCP 具备一个公网（或评审可访问）的 HTTPS 端点，供 SciencePal 沙箱与评审访问。全链路只用环境变量配置，仓库不提交真实令牌。

## 1. 本地启动（本机演示/联调）

```bash
cd sci-weave/centre-control/research-map
# 设置 .env 或导出环境变量（示例见 .env.example）：
#   SCIWEAVE_MAPPING_MCP_HOST / _PORT / _TOKENS_JSON / _CALLER_CAPABILITIES_JSON
#   TerminusDB 连接变量、SQLite 路径、审计库路径
cargo 或 uv run --env-file .env python -m research_mapping.main   # 若已封装，否则按 src/main.py 入口启动
```

验证本机：

```bash
curl -sS -m 10 http://127.0.0.1:<port>/health
curl -sS -m 10 -X POST http://127.0.0.1:<port>/mcp \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'
```

> 管理 MCP 是 Streamable HTTP、Bearer 鉴权、接口层留痕（`ai4-w73z` / `ai4-gvan`）。`/health` 只做最小存活探针，不带令牌。

## 2. 公网发布（两条路径）

### 路径 1：隧道（快速）

```bash
cloudflared tunnel --url http://127.0.0.1:<port>
# 或
ngrok http <port>
```

- 得到形如 `https://xxxx.trycloudflare.com` 的公网地址；MCP 端点即 `<隧道地址>/mcp`，健康端点为 `<隧道地址>/health`。
- 注意：免费版地址会变、域名随机；演示当天提前开隧道并核对地址。
- 令牌仍用 Bearer 鉴权，与本地一致；令牌只存服务器环境变量。

### 路径 2：轻量云

用现成的 compose（`sci-weave/service/` 下的业务项目）或轻量云主机部署 `research-map`，映射 443/80，配置 HTTPS 证书（Caddy / Nginx）。

## 3. 可达性自检（每次演示前）

对 SciencePal 沙箱能用到的同一个公网地址执行：

```bash
# 健康端点
curl -sS -m 10 https://<central-host>/health

# 未鉴权时应返回 401 或健康体的"未鉴权不影响存活"，不返回内部组件详情
curl -sS -i -m 10 https://<central-host>/health | head -20

# 带令牌的 tools/list（只读档）
curl -sS -m 10 -X POST https://<central-host>/mcp \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

# 无令牌时应 HTTP 401，且不创建任何执行/审计事实
curl -sS -o /dev/null -w "%{http_code}" -m 10 -X POST https://<central-host>/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/list","params":{}}'
```

判定：`/health` 200；带令牌 `tools/list` 200 且含 `get_formal_mapping` / `submit_candidate`；无令牌 401。三者满足才进入 SciencePal 演示。

## 4. 安全边界（v869 第 4 条）

- 中央管理 MCP 暴露公网后按 Bearer 鉴权，agent 凭据只开 `read` + `candidate_submit`；
- `candidate_review` / `formalize` 不放给 agent（人工接管点不变）；
- 令牌只存服务器 env，不入仓库、不进演示材料；
- 每次 MCP 调用照常写中央接口层审计账本；
- 提交前跑一次上面的可达性自检，并保留 Replay 链接 + 输出 JSON 双兜底。

## 5. 故障处置速查

| 现象 | 处置 |
| --- | --- |
| `/health` 不通 | 服务未起或隧道失效；先本机 curl 确认，再查隧道进程 |
| `/health` 通但 `/mcp` POST 401 | 令牌错误或未配置；检查服务器 env `_TOKENS_JSON` |
| `tools/list` 缺 `get_formal_mapping` | 版本不匹配；回查 `research-map` 当前工具面 |
| 沙箱内 `/health` 通但 `/mcp` 不通 | 沙箱禁止 POST/非 GET；走路径 B 或兜底 |
| 演示当天地址变更 | 重开隧道后重新跑第 3 节自检；演示材料里的地址以当天实际为准 |