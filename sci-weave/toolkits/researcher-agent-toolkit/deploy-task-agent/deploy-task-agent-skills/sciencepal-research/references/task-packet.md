# 任务包

任务包是协作者交给 SciencePal 的完整指令。它必须能独立回答：目标是什么、输入是哪一版、怎么跑、产物是什么、怎么算通过。

```json
{
  "schema_version": 1,
  "map": {
    "mapping_domain_id": "iris-demo",
    "formal_revision_id": "rev-7",
    "task_node": {"logical_id": "task:t1", "version_id": "t1-v1"},
    "acceptance_criteria": ["150 行、4 特征列、3 类各 50", "无缺失值"],
    "owner": "person:alice"
  },
  "upstream": [
    {"node": "task:t0", "artifact": "resource-version:55", "sha256": "..."}
  ],
  "inputs": [
    {"name": "iris_data.csv", "path": "inputs/iris_data.csv", "sha256": "..."},
    {"name": "check_iris_input.py", "path": "inputs/check_iris_input.py", "sha256": "..."}
  ],
  "constraints": {
    "deterministic": true,
    "params": {"k": 3, "seed": 20261023, "split": "70/30"},
    "network": false,
    "language": "zh-CN"
  },
  "expected_outputs": [
    {"name": "report.md", "kind": "report"},
    {"name": "result.json", "kind": "data"}
  ],
  "provenance": {
    "execution_id": "exec-...",
    "collaborator_id": "agent:data-collaborator",
    "requested_by": "person:alice"
  }
}
```

## 指令骨架

```text
你是 <discipline> 科研执行 agent。
目标：<task_node 目标>
必须满足的验收条件：<acceptance_criteria>
输入文件：<inputs，绝对路径 + sha256>
固定参数：<constraints.params>
运行方式：<固定命令，例如 python check_iris_input.py iris_data.csv>
输出要求：
1) 最终报告写到 report.md；
2) 结构化结果写到 result.json；
3) 不修改输入文件；不联网（除非任务明确允许）。
完成后列出所有产物路径和关键指标。
```

## 规则

- 核心计算优先用上传的固定脚本，不让模型自由选参数。
- 每个输入都要有 sha256；上传后不要改文件。
- 期望产物要写成文件，不要只依赖聊天回答。
- 任务包哈希（canonical JSON）同时写进指令和报告，便于核对“跑的是哪一版任务”。
