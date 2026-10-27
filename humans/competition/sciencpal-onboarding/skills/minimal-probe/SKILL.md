---
name: sciweave-minimal-probe
description: 验证 SciencePal 沙箱三项最小能力：脚本执行、沙箱出站、中央 MCP 通道。结果只用于对接判定（ai4-v869）。
---

# SciencePal 最小能力验证

这是 SciWeave 中央服务对接前的探针，不做业务。执行它并如实记录每一项的结果。

## 任务步骤

### 1. 环境自检

运行并记录：

```bash
python --version
```

### 2. 运行 T1 数据检查（脚本执行探测）

先把 `humans/competition/demo-evidence/` 下的 `check_iris_input.py` 与 `iris_data.csv` 上传到沙箱的同一目录。仓库里不再维护 `checks/` 副本，`demo-evidence/` 是唯一来源。

在沙箱内运行（脚本与数据同目录）：

```bash
python check_iris_input.py iris_data.csv
```

记录输出。预期 `status: ok`。若文件缺失，先检查上传；仍失败则如实记录错误文本。

### 3. 沙箱出站探测（中央端点）

对以下端点发一次 HTTP GET（`<CENTRAL_HEALTH_URL>` 由环境变量或用户提供；未提供时跳过并标注 "not configured"）：

```bash
curl -sS -m 10 <CENTRAL_HEALTH_URL>
```

若平台限制 curl，用 Python：

```python
import urllib.request
print(urllib.request.urlopen("<CENTRAL_HEALTH_URL>", timeout=10).read().decode())
```

## 输出要求

- 逐项输出 `PASS` / `FAIL` / `SKIPPED`，附实际命令与输出文本。
- 不要猜测、不要改写输出。
- 结论行必须三选一：`path_a_feasible` / `path_b_feasible` / `egress_unavailable`。
