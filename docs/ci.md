# 持续集成

回归矩阵是**一个脚本**，本地和任何 CI 都调用它；流水线文件只负责在什么时候调。

## 本地跑

```powershell
# Windows：完整矩阵（Python + 前端 + 语法 + 空白检查）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci.ps1

# 只跑 Python，或只跑某几个子项目
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci.ps1 -SkipWeb
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci.ps1 -Filter 'research-'

# 连真实 TerminusDB 的集成用例一起跑（需要本机库可达）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci.ps1 -Integration
```

```bash
scripts/ci.sh                  # 等价矩阵
scripts/ci.sh --skip-web
scripts/ci.sh --integration
scripts/ci.sh --filter research-
```

退出码非零表示有阶段失败。脚本最后会打印「通过 N / 共 M 个阶段」和失败阶段名。

## 它跑什么

| 阶段 | 内容 |
| --- | --- |
| Python 矩阵 | 每个子项目 `uv run --with pytest --with pytest-asyncio pytest tests -q` |
| 语法检查 | 所有 `src/` 目录 `python -m compileall`，覆盖测试没导入到的文件 |
| 前端 | `web-ui` 的 `npm run test`（vitest）与 `npm run build`（vue-tsc + vite build） |
| 空白 | `git diff --check`，拦截行尾空白与冲突标记 |

子项目位置**不写死**：脚本用 `git ls-files '*tests/test_*.py'` 反推，所以新增子项目自动纳入，未跟踪的本地残留目录不会被误当成 CI 目标。

当前矩阵：16 个测试位置、785 项用例通过、22 项默认跳过（需要真实 TerminusDB / Kafka 的集成用例）。

## 关于「已跳过」

默认不设 `SCIWEAVE_RUN_TERMINUSDB_INTEGRATION`，依赖真实库的用例会自行 skip。这**不是**静默通过：脚本会明确打印跳过了多少项，加 `-Integration` / `--integration` 才执行。

集成用例需要：

- 本机 TerminusDB 可达（`docker compose -f sci-weave/service/terminusdb/compose.yaml up -d`）；
- research-wiki 的 `SCIWEAVE_WIKI_TERMINUSDB_URL` / `_DATABASE` / `_STORE` 已配置，否则会从 skip 变成断言失败。

## 流水线

`.github/workflows/ci.yml` 已提交：矩阵只做一件事——在 ubuntu 与 windows 上装 uv / Node 后执行 `scripts/ci.sh`。该文件通过 YAML 语法校验。

**待决**：仓库托管在 Gitee，GitHub Actions 不会执行这个文件。要真正跑起来，需要二选一：

1. 用 Gitee Go 写流水线（Gitee 自有格式，需要真实 schema 与 runner，尚未接）；
2. 把仓库镜像到 GitHub，或给 Gitee 配自托管 runner 直接调 `scripts/ci.sh`。

两者都要账户侧操作，不在代码层。在决定之前，矩阵的价值来自**本地可复现**：任何人一条命令就能跑出与 CI 相同的结果。

## 已知限制

- `scripts/ci.sh` 只做过 `bash -n` 语法检查，**没有在 Linux/macOS 上实跑**（开发机是 Windows）。首次在非 Windows 环境使用需补测。
- 证据包（`humans/competition/demo-evidence/`）按字节固定 SHA256，Windows 上 `core.autocrlf=true` 会把工作区改写成 CRLF 导致假失败。`.gitattributes` 已把这些文件钉成 `eol=lf`；已存在的克隆需要重新检出一次该目录。
- 前端 `npm run build` 含类型检查，但它只在 `web-ui` 上跑，不覆盖其它前端目录。
