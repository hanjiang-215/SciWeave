---
name: deploy-task-agent-sciencepal-research
description: 把需要真实计算的科研任务委派给 SciencePal 领域 Agent，收集沙箱产物并写成可审核的执行报告。
---

# 用 SciencePal 执行科研任务

你是协作者 Agent。当任务需要真实的数据分析、材料/生物/蛋白/血浆计算或专利检索，而本地没有对应执行环境时，用 `sciencepal` MCP 把任务交给 SciencePal；你负责组织任务、验收结果、写报告，不负责重算。

## 什么时候用

用：

- TaskNode 的完成条件需要跑代码、处理数据、生成图表或领域计算；
- 需要 SciencePal 的领域 Agent（biology / material / protein / plasma / patent / general）；
- 结果要作为可核验证据进入草稿箱，需要 `run_id` 与产物哈希。

不用：

- 只是改写、总结、翻译已有文本；
- 任务可以用现有脚本在本机确定性地完成，且不需要 SciencePal 执行记录；
- 需要修改正式 Research Mapping（那走候选流程，不是 SciencePal）。

## 前置检查

1. 确认 `SCIENCEPAL_ACCESS_TOKEN` 已配置；没有就返回 `sciencepal_token_missing`，不要重试。
2. 用 `sciencepal_agents` 确认目标领域 Agent 的 `agent_id`；不确定时让 `agent_select_type=auto`，并在报告里记录实际 Agent。
3. 从地图读取**固定 revision** 的任务切片，不要读“最新图”。

## 协议

1. **取任务**：用 `research-mapping.get_formal_mapping_at_revision`，参数是交接消息里的 `trigger_revision_id`。拿到节点目标、验收条件、上游输出引用。
2. **组任务包**：按 `references/task-packet.md` 组装。输入文件先落到工作区，算 sha256；核心计算写死命令与参数（K、种子、划分比例），不要让模型自由选择。
3. **发起**：调 `sciencepal_start`，`idempotency_key` 用 `exec:<execution_id>`，把任务包里的 `instruction`、`files_json`、`agent_id` 传进去。拿到 `run_id` / `thread_id` 立刻记下，告诉负责人“已发起，ID=…”。
4. **轮询**：`sciencepal_status`，20–30 秒一次，指数退避到 60 秒。不要忙等；单次轮询失败可重试，连续 3 次 `sciencepal_unavailable` 再判失败。
5. **收产物**：状态 `completed` 后调 `sciencepal_collect`。核对期望产物是否齐全、sha256 是否与下载内容一致。
6. **验收**：逐条对照验收条件，能由产物直接证明的才写 `met: true`；不能证明的写 `met: false` 并说明缺什么。不要用模型口述代替产物。
7. **写报告**：按下面的 ExecutionReport 结构输出 JSON，作为草稿 payload。运行失败也要写报告，状态为 `failed`，保留错误码与 `run_id`。
8. **路线变更**：如果结果说明需要新增/修改节点或依赖，在报告的 `route_change` 里给建议变更集；由人提交候选，你不要直接改正式图。

## ExecutionReport

```json
{
  "schema_version": 1,
  "task_node_id": "task:t1",
  "execution_id": "exec-...",
  "status": "completed | failed | needs_revision",
  "summary": "一句话结论",
  "sciencepal": {
    "run_id": "...",
    "thread_id": "...",
    "agent_id": "...",
    "model": "...",
    "duration_s": 42
  },
  "inputs": [{"name": "iris_data.csv", "sha256": "..."}],
  "artifacts": [
    {"name": "report.md", "path": "runs/<run_id>/report.md",
     "kind": "report", "sha256": "..."}
  ],
  "acceptance": [
    {"criterion": "150 行、4 特征、3 类各 50", "met": true, "evidence": "result.json"}
  ],
  "findings": ["..."],
  "limitations": ["..."],
  "route_change": {
    "needed": false,
    "proposal": {"nodes": [], "edges": [], "rationale": ""}
  }
}
```

硬规则：

- 没有 `run_id` 或没有产物哈希的“结果”，不得写成 `completed`。
- 报告里的数字必须能在产物或 `status` 返回里找到出处。
- 不把 SciencePal 的模型口述当作实验结论；结论必须能指到产物。
- 不把令牌、沙箱临时 URL、完整异常栈写进报告。

## 失败处置

| 现象 | 错误码 | 动作 |
| --- | --- | --- |
| token 缺失/过期 | `sciencepal_token_missing` / `sciencepal_unauthorized` | 停止，通知负责人换 token |
| SciencePal 不可达 | `sciencepal_unavailable` | 重试 3 次后写失败报告，转人工 |
| run 失败 | `sciencepal_run_failed` | 保留 `run_id` 与 `error`，写失败报告 |
| 超时 | `sciencepal_run_timeout` | 停止 run，写失败报告 |
| 没有产物 | `sciencepal_no_artifacts` | 检查任务是否要求写文件；写失败报告 |
| 产物缺件/哈希不符 | `sciencepal_artifact_missing` / `sciencepal_artifact_hash_mismatch` | 不接纳结果，写失败报告 |
| 文件越界 | `sciencepal_workspace_violation` | 修正输入路径，不绕过 |

普通失败只改变执行记录，不改正式路线。只有需要改变目标、依赖或验收条件时，才在 `route_change` 里提建议。
