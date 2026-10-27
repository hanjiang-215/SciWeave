# 证据与报告

## 最小证据集

一次 SciencePal 执行至少留下：

| 证据 | 来源 | 用途 |
| --- | --- | --- |
| `run_id` / `thread_id` | `sciencepal_start` | 能回到 SciencePal 查这次执行 |
| 输入 sha256 | `sciencepal_start` 返回的 `inputs` | 证明跑的是哪一版输入 |
| 产物清单 + sha256 | `sciencepal_collect` 的 `artifacts` | 证明结果确实存在且未被篡改 |
| `manifest.json` | `collect` 落盘 | 证据索引，随草稿引用 |
| 验收逐条结论 | 协作者 | 说明哪些条件被满足、依据是什么 |

## 报告要求

- `status=completed` 必须同时满足：run 终态为 `completed`、产物齐全、验收条件逐条有依据。
- 任何一条验收条件没有产物支撑，写 `met: false`，不要写“应该满足”。
- 失败报告保留 `run_id`、错误码、失败阶段；不要写完整异常栈。
- 报告是草稿 payload 的一部分，最终由 TaskNode Owner 审核，不直接成为正式结论。

## 哈希

```text
sha256(file_bytes) 的小写十六进制
```

下载后重新计算，与 `collect` 返回值比对；不一致就按 `sciencepal_artifact_hash_mismatch` 处理。
