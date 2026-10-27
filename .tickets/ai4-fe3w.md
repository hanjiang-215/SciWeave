---
id: ai4-fe3w
status: closed
deps: []
links: []
created: 2026-10-27T01:01:48Z
type: chore
priority: 1
assignee: Frank Qi
parent: ai4-aaff
tags: [chore, demo, evidence]
---
# 演示证据 JSON 是 UTF-16LE 编码，工具链无法直接读取

`humans/competition/demo-evidence/` 下四份证据文件全部是 UTF-16LE + CRLF + BOM：

```text
$ file humans/competition/demo-evidence/*.json
iris_baseline_result.json    Unicode text, UTF-16, little-endian, with CRLF
iris_input_check.json        Unicode text, UTF-16, little-endian, with CRLF
iris_input_failure.json      Unicode text, UTF-16, little-endian, with CRLF
iris_platform_pipeline.json  Unicode text, UTF-16, little-endian, with CRLF, very long lines
```

后果：

```text
$ python3 -c "import json; json.load(open('.../iris_platform_pipeline.json'))"
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte
```

1. `json.load` 直接抛异常，任何自动化校验（包括把证据接进看板或验收脚本）都必须先手工转码。
2. `iris_platform_pipeline.json` 是 67 KB 的治理时间线，也是评审追溯「批准 → 正式化」的唯一机读记录，现在无法被工具读取。
3. Git 把 UTF-16 当二进制处理，`git diff` 看不到内容变化，证据被改动时无人能审。

成因同 `ai4-483l`：这批文件由 Windows 侧的 PowerShell 重定向（`>`）生成，PowerShell 5 默认 `Unicode`（UTF-16LE）编码，随后原样提交。

## Design

1. 四份文件统一转存为 **UTF-8 无 BOM、LF**。内容不动，只改编码与行尾。
2. 生成脚本（`check_iris_input.py` / `run_iris_baseline.py` / `run_iris_mapping_pipeline.py`）都用 `print(json.dumps(...))` 输出到 stdout，编码由调用方决定。在 `demo-evidence/README` 或 `evidence-card.md` 的运行说明里写明用 `... | tee x.json`（或 `python3 x.py | out-file -Encoding utf8NoBOM`）而不是 PowerShell 的 `>`，避免复发。
3. `evidence-card.md` 中对这些文件的表述（如第 26 行、第 39 行的哈希引用）在转码后复核一遍，确保引用值与实际文件一致。
4. 新增 `humans/competition/demo-evidence/README.md`，列出四份证据的生成命令、编码要求和校验方式（`file` + `python3 -m json.tool`）。该目录目前没有 README，命令只散落在 `evidence-card.md` 与 `demo-script.md` 里。

## Acceptance Criteria

- [x] 四份 `*.json` 均为 UTF-8 无 BOM、LF 行尾。
- [x] `python3 -m json.tool` 对四份文件全部解析成功。
- [x] `git diff` 能看到这些文件的内容差异（不再被识别为二进制）。
- [x] 生成命令的编码要求写入 `evidence-card.md` 或新增的 `demo-evidence/README.md`。
- [x] 转码后复核 `evidence-card.md` 引用的哈希与数字与文件内容一致。

## Notes

**2026-10-27 登记（Frank Qi）**

身份核对：本票 assignee 为 Frank Qi，当前分支 `feature/frank-qi`、`git config user.name=Frank Qi`，一致。

不影响演示画面本身（演示时人工打开文件或看 TerminusDB 界面即可），但影响自动化复核与评审追溯，成本极低，建议与 `ai4-483l` 一起做掉。

**2026-10-27 实现与验证（Frank Qi）**

提交：`e7a001f`（`iris_platform_pipeline.json` 转 UTF-8 + 新增 `demo-evidence/README.md`）、`5fe4810`／`c514752`（另三份随脚本重生成）、`f556dba`（证据卡数字复核）。

验证：

```text
$ file humans/competition/demo-evidence/*.json
iris_baseline_result.json      JSON text data
iris_input_check.json          JSON text data
iris_input_failure.json        JSON text data
iris_platform_pipeline.json    JSON text data          # 原为 Unicode text, UTF-16, little-endian, with CRLF

$ python3 -m json.tool  （四份）→ 全部解析成功
$ git diff 0d829ad^ 0d829ad -- iris_platform_pipeline.json
 61 insertions(+), 57 deletions(-)                     # 已是文本 diff，不再是 Bin 67,522 -> 33,572 bytes
```

**内容等价性单独验证过**：把父提交的 blob 按 UTF-16 解码、与转码后的 UTF-8 内容做 `==` 比较，结果为 `True`。转码只改编码、行尾与缩进（67,522 → 33,572 字节），不动任何字段。

**一处超出 AC 的连带修改**：`evidence-card.md` 原文写「快照文件 4,615 字节」「SHA-256 `daaeb5e3…`」，这两个值描述的是 CRLF 副本，与仓库内 LF blob（4,464 字节）不符。已在 `5fe4810` 一并改正为「仓库内 LF，4,464 字节；官方下载为 CRLF，4,615 字节」，哈希改为归一化后的值。不修的话，本票「复核哈希与数字一致」这一条自相矛盾。

**编码要求写在哪里**：新增的 `humans/competition/demo-evidence/README.md`，含生成命令、`file` 与 `json.tool` 校验方式，以及 PowerShell 5 用 `Out-File -Encoding utf8NoBOM` 而不是 `>` 的具体反例——这次的问题正是 `>` 默认输出 UTF-16LE 造成的。

**遗留**：无。
