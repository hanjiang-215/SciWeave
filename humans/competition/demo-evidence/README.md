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

两个脚本各自持有一份 `sha256_of`，是**两份独立副本，必须同步修改**。不把它们抽成共享模块是有意的：两者都要能作为单文件脚本被上传到 SciencePal 沙箱的扁平目录里单独运行，多一个依赖文件就破坏了这一点。`ai4-3vkc` 合并的是 `demo-evidence/` 与 `sciencpal-onboarding/checks/` 之间的副本，跟这两个脚本无关，不要指望任何票据会自动合并它们。

`tests/test_check_iris_input.py` 里有一条一致性测试，断言这个哈希在 `check_iris_input.py`、`run_iris_baseline.py`、本 README、`evidence-card.md`、`sciencpal-onboarding/agent/t2-baseline-agent.md` 五处同时是当前值、且没有一处残留旧值。改哈希时它会失败，这是有意的。

## 测试

```bash
cd humans/competition/demo-evidence
python3 -m unittest discover -s tests -q
```

测试只断言脚本的公开行为：`check(path)` 返回的记录、`main()` 打印的记录与退出码。不测试内部函数。

## 判定顺序

T1 与 T2 都是**结构判定在前、溯源判定在后**。这条顺序很关键：任何通过哈希校验的文件必然就是锁定快照，所以哈希若排在最前面，行数、缺失值、类别计数这些更具体的失败就永远不会被报告——它们会全部退化成 `source_hash_mismatch`。

因此哈希检查放在**最后**：结构检查先跑完并各自给出理由码，哈希作为成功前的最后一道门。这既满足「缺列要报 `missing_columns`」，也保住其余四种诊断，而且溯源判定没有被削弱——数值被改动的文件结构全对，最后仍会被哈希拦下。

T1 的理由码：

| `reason_code` | 含义 |
| --- | --- |
| `missing_columns` | 必需列缺失 |
| `row_count_mismatch` | 行数不是 150 |
| `missing_values` | 存在空值或无法解析为数值的特征 |
| `class_count_mismatch` | 三类计数不是各 50 |
| `unreadable_input` | 文件不可读或不是合法 UTF-8 |
| `source_hash_mismatch` | 内容与固定快照不一致 |

T2 只做上游已固定的结构检查，理由码是 `missing_columns`、`invalid_values`、`unreadable_input`、`source_hash_mismatch` 四个——行数与类别计数由 T1 负责，T2 不重复。

两个脚本的任何失败都以结构化 JSON 报告、退出码 1，不会抛出 traceback。漏传文件、误传 UTF-16 副本这类操作失误同样走 `unreadable_input`。
