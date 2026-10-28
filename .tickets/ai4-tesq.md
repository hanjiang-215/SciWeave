---
id: ai4-tesq
status: open
deps: [ai4-1aeg, ai4-e959, ai4-349h]
links: [ai4-8d9j, ai4-349h, ai4-k2le, ai4-8dgd]
created: 2026-10-28T01:06:30Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-yidf
tags: [centre-control, centre-agents, agent, correctness, ready-for-agent]
---
# 中央 Worker 注入 mcp.servers：模型第一次拿到工具

中央 Worker 起 fast-agent 时，`@fast.agent(...)` 没有 `servers=` 参数，`_write_fast_agent_config()` 写的配置文件只有 `compaction: auto: false` 和 `session_history: true`，没有 `mcp.servers` 块。

所以模型手里一个工具都没有。它读不到 `list_reviewable_candidates`，也写不了 `append_prereview_log`。中央 Agent 的唯一职能因此完全无法履行。

套件侧的 `mcp_servers.py` 已经解决过这个问题：卡片 → `mcp.servers`，三处翻译（`streamable-http` → `http`、`url_env` → `url`、`project_dir_env` → `cwd`），缺环境变量直接抛错而不是静默跳过。中央侧要一份同形状的实现。

已验证：中央套件那六张卡能被套件的加载器读进来，并渲染出正确的 `mcp.servers` 块。所以缺的不是卡片，是中央侧的加载与渲染。

规格见 `docs/superpowers/specs/2026-10-28-centre-agent-runtime-template-port-design.md`。

## Acceptance Criteria

- [ ] 中央侧有一个独立的卡片加载层，读套件目录下的 `mcp/*/mcp.json`，不复制卡片
- [ ] 生成 fast-agent 配置时按声明资源写出 `mcp.servers`，transport 与 url 正确
- [ ] 缺必填环境变量时抛错，错误里带变量名与卡片名，不得静默跳过该卡
- [ ] 未知资源名（声明了但目录里没有）抛错，不得静默忽略
- [ ] `fast.agent(...)` 真的收到 `servers=` 参数，有测试检查框架收到的 kwargs
- [ ] 卡片里不得出现 `formalize_candidate` / `formalize_wiki` / `decide_wiki_review` / `record_review`，静态校验仍通过

