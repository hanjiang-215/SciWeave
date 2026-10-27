---
id: ai4-oq1m
status: in_progress
deps: []
links: []
created: 2026-10-27T03:01:34Z
type: chore
priority: 2
assignee: hanjiang
tags: [ci, infra]
---
# 补上持续集成：可移植测试脚本与 Gitee 流水线

全仓无 .github/.gitee 流水线，集成测试默认跳过（SCIWEAVE_RUN_TERMINUSDB_INTEGRATION 未设时为 7 项），回归只能靠人工逐个 uv run。10-22 评审已把「没有 CI」列为第 3 风险，至今未动。

## Design

分两层：repo 内的 scripts/ci.ps1 与 scripts/ci.sh 跑完整矩阵（13 个测试位置的 pytest + web-ui 的 vitest + compileall + git diff --check），本地与任何 CI 都能调用；再加一层流水线定义。仓库托管在 Gitee，GitHub Actions 不会执行，需确认用 Gitee Go 还是自托管 runner，未确认前先交付可移植脚本并把流水线文件留为待接线。

## Acceptance Criteria

1) scripts/ci.ps1 与 ci.sh 能在本地跑完整个矩阵并给出非零退出码表示失败；2) 脚本按子项目输出通过/失败汇总；3) 集成测试默认跳过时明确打印「已跳过 N 项真实库用例」而不是静默；4) 流水线定义文件提交并能通过语法校验；5) 真实流水线执行需远端 runner，若不可用在本票如实标注，不把未执行写成已通过；6) README 或 docs 记录本地用法。

## Notes

**2026-10-27 交付（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`，三者一致。

交付：

- `scripts/ci.ps1` / `scripts/ci.sh`：完整矩阵。子项目位置不写死，从 `git ls-files '*tests/test_*.py'` 反推，新增子项目自动纳入，未跟踪的本地残留目录不会被误判。
- `.github/workflows/ci.yml`：ubuntu + windows 双平台，只负责装 uv/Node 后调用 `scripts/ci.sh`。
- `docs/ci.md`：本地用法、阶段说明、跳过语义、待决项与已知限制。

**修正票面事实**：票里写的「13 个测试位置」不准。按 git 索引实际是 **16 个**（含 `humans/competition/demo-evidence`）。`sci-weave/task-agent/` 下有 tests 目录但 `git ls-files` 为 0 个文件，是本机未跟踪残留，不属于仓库、未纳入矩阵。

验证（本机 Windows，完整矩阵）：

```text
通过 20 / 共 20 个阶段，pytest 用例 785 项通过
已跳过 22 项（默认为依赖真实 TerminusDB / Kafka 的集成用例）
npm run test      PASS    7.6s
npm run build     PASS   21.8s
compileall        PASS   15 个 src 目录
git diff --check  PASS
```

验收对照：

1. 两个脚本跑完矩阵、失败时 `exit 1` ✓（另测 `-Filter shared` 子集 exit 0）
2. 逐子项目 `PASS/FAIL` 行 + 通过数/跳过数/耗时，末尾汇总失败阶段名 ✓
3. 未开集成时打印「集成用例：跳过（设 -Integration 或 …=1 执行）」，汇总再打印「已跳过 N 项」 ✓
4. `.github/workflows/ci.yml` 已提交，pyyaml 解析通过 ✓
5. **真实流水线未执行**：仓库在 Gitee，GitHub Actions 不会跑该文件；Gitee Go 需要账户侧配置与自有 schema，未接。已在票和 `docs/ci.md` 写明，不计为通过 ✓
6. `docs/ci.md` 记录本地用法 ✓

过程中修掉一个会让矩阵在 Windows 上**假失败**的问题：

`humans/competition/demo-evidence` 的证据文件按字节固定 SHA256，而本机 `core.autocrlf=true` 把工作区换行改写成 CRLF，导致 `test_crlf_copy_of_the_same_content_passes` 等 2 项失败（blob 本身是 LF，git 视角无改动）。新增 `.gitattributes` 把该目录钉成 `eol=lf` 并重新检出，20 项全通过。这类失败不是代码缺陷，但足以让人误判 CI 红。

未验证项：

- `scripts/ci.sh` 只做了 `bash -n` 语法检查，**没有在 Linux/macOS 实跑**（开发机无可用 WSL 发行版）。首次在非 Windows 环境使用需补测。
- 集成模式（`-Integration`）本次未跑：真实库用例另需 wiki 变量齐备，留待有 TerminusDB 的环境验证。


