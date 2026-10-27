---
id: ai4-tve9
status: closed
deps: []
links: []
created: 2026-10-27T11:33:22Z
type: bug
priority: 1
assignee: hanjiang
tags: [ci, infra]
---
# CI 汇总把单个失败阶段报成全过，且矩阵数字与文档不符

`scripts/ci.ps1` 的汇总行在**恰好一个阶段失败**时报告「全部通过」。

实测复现（2026-10-27，本机）：

```text
=== 语法检查（compileall） ===
  FAIL
...
=== 汇总 ===
  通过 21 / 共 21 个阶段，pytest 用例 861 项通过
  失败阶段：
    - compileall（exit 1）
```

根因：第 171 行 `($results.Count - $failed.Count)`。当 `Where-Object` 只匹配到一个对象时，`$failed` 不是数组，`$failed.Count` 求值为 `$null`，`21 - $null = 21`。退出码仍是 1，所以门禁没坏，坏的是给人看的数字——而这正是所有人扫 CI 时唯一会读的那一行。

同时 `docs/ci.md:39` 写「16 个测试位置、785 项用例通过」，当前 HEAD 实际是 **17 个位置、861 项通过、22 项跳过**。

## Acceptance Criteria

- [x] 汇总行在「0 个 / 1 个 / 多个」阶段失败三种情形下都报出正确数字；用一个可复现的最小用例证明单个失败不再被算成通过。
- [x] `docs/ci.md` 的测试位置数、用例数、跳过数与当前 HEAD 实跑一致。
- [x] 全量 `scripts/ci.ps1` 跑一遍，汇总数字与 861 项、22 跳过对得上。


## Notes

**2026-10-27T11:51:16Z**

## 2026-10-27 修复

**根因**：`$failed` 用 `Where-Object` 管道赋值。管道只输出一个对象时，赋值结果是标量而不是数组，标量没有 `Count`，`$null` 参与算术被当成 0，于是 `21 - $null = 21`。

**改动**（`scripts/ci.ps1`）：
- `$failed = @($results | Where-Object { $_.Exit -ne 0 })`，并在原地留注释说明为什么必须包数组。
- 同时修掉同阶段的第二个「假绿」：`compileall` 原本把 pyc 写进各 `src/` 的 `__pycache__`，一旦上一次的 pyc 还在就不用重写，于是缓存干净的机器上首跑必红、缓存机器上永远 PASS。改为设置 `PYTHONPYCACHEPREFIX=<repo>/var/pycache-ci` 并在每次运行前清空；`scripts/ci.sh` 同步。
- `docs/ci.md`：位置数与用例数改为 17 / 863，补一段说明字节码缓存位置与数字以汇总行为准。

**验证**：
1. 真实单点失败场景（给一个被跟踪文件加行尾空白，让 `git diff --check` 失败，其余两阶段通过）：
   - HEAD 版本：`通过 3 / 共 3 个阶段` + `失败阶段：git diff --check（exit 2）` ← 复现了缺陷
   - 修复版本：`通过 2 / 共 3 个阶段` + 同一失败阶段
2. 删掉全部 743 个 `__pycache__` 后首跑全量：`21/21 阶段通过，863 项用例，22 项跳过`，语法检查阶段 `PASS 16 个 src 目录`，`src/` 下不再产生 `__pycache__`。
3. `ci.sh` 的汇总用 `FAILED=()` 数组与 `${#FAILED[@]}`，不受本缺陷影响，只同步了字节码缓存位置。

`uv run` 起头的 python 在本机 DSH 沙箱下无法写 `sci-weave/**/src/`，这是环境限制、不是仓库缺陷；改成把字节码写到 `var/` 之后这个限制也不再影响该阶段。
