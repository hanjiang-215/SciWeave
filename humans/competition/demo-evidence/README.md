# 演示证据与执行脚本

`ai4-aaff`（SciWeave 默认科研示例场景）的最小数字证据包。本目录同时是**运行入口**和**证据存放处**：脚本在这里执行，结果 JSON 也在这里落盘。

`evidence-card.md` 是给人看的证据卡，引用本目录的文件与数值；本 README 只讲怎么重新生成这些文件。两者冲突时以实际文件内容为准，并修正 `evidence-card.md`。

## 文件

| 文件 | 说明 |
| --- | --- |
| `iris_data.csv` | UCI Iris 官方快照（`https://archive.ics.uci.edu/static/public/53/data.csv`，DOI `10.24432/C56C76`，CC BY 4.0） |
| `iris_data_failure_inject.csv` | 失败注入副本：移除 `class` 列，用于演示 T1 拦截 |
| `check_iris_input.py` | T1 输入检查，仅标准库 |
| `run_iris_baseline.py` | T2 确定性 KNN 基线（K=3、种子 `20261023`、测试占比 0.3），仅标准库 |
| `run_iris_mapping_pipeline.py` | 平台治理链路（真实 TerminusDB + 管理 MCP），需要本机 TerminusDB |
| `iris_input_check.json` | T1 通过记录 |
| `iris_input_failure.json` | T1 失败注入记录 |
| `iris_baseline_result.json` | T2 运行结果 |
| `iris_platform_pipeline.json` | 治理链路完整时间线 |
| `tests/` | T1/T2 脚本的行为测试 |

## 重新生成证据

```bash
cd humans/competition/demo-evidence

python3 check_iris_input.py iris_data.csv > iris_input_check.json
python3 check_iris_input.py iris_data_failure_inject.csv > iris_input_failure.json   # 预期退出码 1
python3 run_iris_baseline.py iris_data.csv > iris_baseline_result.json
```

治理链路的命令与前置（TerminusDB 需先启动、凭据走环境变量）见 `evidence-card.md`。

## 编码要求

**证据 JSON 必须是 UTF-8 无 BOM、LF 行尾。** 历史上这批文件由 Windows PowerShell 的 `>` 重定向生成，PS 5 默认输出 UTF-16LE + CRLF + BOM，导致：

- `json.load()` 抛 `UnicodeDecodeError`，任何自动化复核都要先手工转码；
- Git 把文件当二进制，`git diff` 看不到内容变化，证据被改动时无法审查。

用上面的 `>` 在 bash 或 PowerShell 7+（默认 UTF-8）下执行即可。若在 Windows PowerShell 5 里操作，改用：

```powershell
python .\check_iris_input.py .\iris_data.csv | Out-File -Encoding utf8NoBOM iris_input_check.json
```

校验：

```bash
file *.json                      # 应为 "JSON text data"，不是 "UTF-16"
python3 -m json.tool iris_input_check.json > /dev/null
```

## 快照哈希

快照哈希按**内容**计算：读取全部字节后把 `\r\n` 归一化为 `\n` 再取 SHA-256。这样 LF 检出（本仓库）与 CRLF 检出（官方下载、Windows 工作副本）得到同一个值，快照校验只对内容敏感，不对检出工具的换行策略敏感。

当前固定值：`ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4`

两个脚本共用同一实现；改动其中一处时另一处必须同步，直到 `ai4-3vkc` 把副本合并为单一来源。

## 测试

```bash
cd humans/competition/demo-evidence
python3 -m unittest discover -s tests -q
```

测试只断言脚本的公开行为：`check(path)` 返回的记录、`main()` 打印的记录与退出码。不测试内部函数。

## 判定顺序

T1 与 T2 都**先结构后溯源**：列缺失属于结构性失败，先于哈希比对报告；列齐全但数值被改动的文件由哈希拦下。两类失败各有自己的 `reason_code`：

| `reason_code` | 含义 |
| --- | --- |
| `missing_columns` | 必需列缺失，属结构错误 |
| `source_hash_mismatch` | 内容与固定快照不一致，属溯源错误 |
| `row_count_mismatch` / `missing_values` / `class_count_mismatch` | 行数、缺失值、类别计数不符 |
