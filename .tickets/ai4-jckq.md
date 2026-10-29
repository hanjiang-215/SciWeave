---
id: ai4-jckq
status: in_progress
deps: []
links: [ai4-v869, ai4-roow, ai4-aaff, ai4-v19u, ai4-sman, ai4-fm4a]
created: 2026-10-27T04:00:51Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-v869
tags: [enhancement, ready-for-agent, sciencepal, harness, agent]
---
# SciencePal 套件跨 harness 接入：MCP、CLI 与 Skill 安装契约

让 WorkBuddy、DSH 或其他集成 Agent 在不改 SciWeave runtime 的前提下安装 SciencePal 能力：同一套 Skill + bridge，支持 stdio/HTTP MCP 与 CLI；SciWeave 只保留地图、草稿与治理。真实 SciencePal run 已跑通，剩余跨 harness 安装矩阵、失败样本与第一个真实 harness 的实测。

## Design

宿主边界：协作者运行在外部 harness；SciWeave 不部署、不托管 harness，只提供地图、草稿箱与治理 MCP。SciWeave Task Agent 不再是主路径。

三种接口：Skill（决策协议）、CLI（任何有 shell 的 harness）、MCP（stdio 与本地 HTTP，优先）。三者行为一致，输出 JSON；CLI 退出码 0/1/2。

产物契约：上传文件落 /workspace；产物收 /outputs 与 /workspace/outputs（同一份，按 name+sha256 去重）；跳过 /workspace/skills、memory、_refs。

与 v869 的关系：v869 的路径 A（中央 MCP 公网）仍是可选项；本票覆盖不依赖公网的本地 bridge，且不要求改 fast-agent runtime。

不做：不改 research-map/buffer/coordinator/队列/看板；不把 formalize 下放；不把运行状态写进 TaskNode 版本对象。

## Acceptance Criteria

- `sciencepal agents/start/status/collect` 四条命令在真实 token 下可用，输出单行 JSON，退出码符合 0/1/2。
- stdio MCP 与 HTTP MCP 均可 initialize；至少列出 5 个工具。
- Skill、harness 安装矩阵、generic MCP 配置齐备；WorkBuddy 或 DSH 至少一个真实安装并跑通一次 start→collect。
- 真实 run 证据：run_id、status、耗时、产物 sha256、上传/输出目录；错误路径 token 缺失与 401 有稳定错误码。
- 不修改中央服务与现有 runtime 的默认行为；新增文件有单测。


## Notes

**2026-10-27T04:03:15Z**

2026-10-27 套件已具备三种调用方式：stdio MCP（5 工具）、本地 HTTP MCP（initialize 200）、CLI（agents/start/status/collect/cancel，JSON 输出，退出码 0/1/2）。新增 harness/README.md 与 generic-mcp.json；Skill 增加 CLI 与 harness 参考。真实 smoke 与 12 项单测通过。未完成：WorkBuddy/DSH 实际安装、T1/T2 真实执行；保持 in_progress。
