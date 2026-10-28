---
id: ai4-0vnn
status: open
deps: []
links: [ai4-grlc]
created: 2026-10-27T17:00:10Z
type: chore
priority: 2
assignee: hanjiang
tags: [ci, linux, dx, runtime, cross-platform]
---
# Linux 跨平台验证：runtime 红测试在容器内实锤，含挂载假象澄清

Linux 容器实跑 runtime 全量测试的跨平台验证证据：在 python:3.12-slim 容器内 uv sync --locked 后跑 unittest discover -s tests，106 条测试中恰好 1 条失败（test_a_session_dir_cannot_escape_the_home，ValueError not raised）——与 ai4-grlc 第一条缺陷的描述完全一致；Windows 上同一套测试 106 条全绿。另澄清：此前仅挂载 runtime 目录时出现的 draft-buffer 卡片加载失败与 service-template FileNotFoundError 是挂载范围不全造成的假象，挂载整个 deploy-task-agent 后消失，不是真实缺陷。复现命令与完整输出见本票 Notes。

## Design

本票是 ai4-grlc（Frank Qi）的跨平台验证证据补充：CI 从未在 Linux 真跑，Windows 绿 Linux 红的缺陷只有换平台才能暴露。为不越权编辑 Frank Qi 的票，另立本票记录复现证据并 links 关联原票。

## Acceptance Criteria

- [x] 记录 Linux 容器复现命令与失败输出（已在 Notes）
- [x] 与 ai4-grlc 的第一条缺陷（session_dir 盘符/反斜杠逃逸校验）核对一致
- [x] 说明挂载假象（draft-buffer / service-template 两条错误非真实缺陷）
- [ ] 结论进入 ai4-grlc 的处置路径（由 Frank Qi 或转交后修复）

## Notes

**2026-10-27T17:05:00Z**

**2026-10-27 复现（hanjiang，assigned）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`，三者一致。本票 LINKS `ai4-grlc`（Frank Qi），不编辑原票正文，仅作跨平台验证证据。

### 复现命令（Linux 容器，正确挂载整个套件）

```bash
docker run --rm -v "$PWD/toolkits/researcher-agent-toolkit/deploy-task-agent:/toolkit" \
  -w /toolkit/runtime python:3.12-slim \
  bash -lc "pip install -q uv && uv sync --locked -q && uv run python -m unittest discover -s tests"
```

### 结果

```text
Ran 106 tests in 10.395s
FAILED (failures=1)

FAIL: test_a_session_dir_cannot_escape_the_home (test_fast_agent_runtime.SettingsTests.test_a_session_dir_cannot_escape_the_home)
  File "/toolkit/runtime/tests/test_fast_agent_runtime.py", line 139, in test_a_session_dir_cannot_escape_the_home
    with self.assertRaises(ValueError):
AssertionError: ValueError not raised
```

与 `ai4-grlc` 第一条缺陷描述**逐字吻合**：`session_dir="C:/absolute"` 在 POSIX 上 `Path("C:/absolute").is_absolute()` 为 `False`、`parts=('C:', 'absolute')`，校验的两个条件都不成立 → `ValueError` 不抛。另验证反斜杠形态 `..\..\outside` 在 POSIX 上 `parts` 只有一个元素，同样逃逸。Windows 上同一套测试 106 条全绿——**Windows 绿、Linux 红的缺陷只有换平台才能暴露**，印证了「CI 从未在 Linux 真跑」的判断（docs/ci.md 待决项）。

### 挂载假象澄清（重要）

第一版复现只挂了 `runtime/` 目录，出现额外失败：`test_standard_cards_load_and_expose_real_tool_surface`（`draft-buffer not found`）和 `service-template/gateway/subscriber/src/main.py FileNotFoundError`。换成挂载整个 `deploy-task-agent` 后**这两条全部消失**——它们是挂载范围不全导致的假象（测试用 `parents[2]/libs/mcp-libs` 与套件兄弟目录），**不是真实缺陷**。请 Frank Qi 修复 `ai4-grlc` 时不必理会这两条。

### 处置建议

- 第一、三条缺陷（session_dir 校验、Workflow YAML 双份）在原票范围内，可直接按原票 AC 修复；
- 本票结论已进入 `ai4-grlc` 的处置路径；若需在本仓库落地 Linux 侧验证，可后续在 docs/ci.md 的待决项落地时顺带纳入矩阵。

### 修复方案可行性验证（2026-10-28，Linux 容器 python:3.12-slim）

按 `ai4-grlc` 第一条缺陷提出的校验思路（盘符形态 + 反斜杠逃逸 + 保留 is_absolute/dot 检查）在 Linux 上模拟三种输入 + 一条合法路径：

```text
C:/absolute (盘符)           → reject=True (drive_letter)
C:\absolute (盘符反斜杠)     → reject=True (drive_letter)
..\..\outside (反斜杠逃逸)   → reject=True (backslash_escape)
relative/subdir (合法相对)   → reject=False (accepted)
```

**结论**：提议方案在 POSIX 上可正确拦截全部三种逃逸形态、不误伤合法相对子目录，修复路径可行。注意补测试时除 `C:/absolute` 外还应覆盖 `C:\absolute` 与 `..\..\outside` 两种输入（`ai4-grlc` AC 第一条已列）。

**2026-10-28T01:35:00Z**

前三条 AC 已勾（复现命令、与 grlc 第一条核对一致、挂载假象澄清），本票保持 open：第四条「结论进入 ai4-grlc 处置路径」等待 Frank Qi 修复或转交后闭合。

**2026-10-28T02:50:00Z**

补充：runtime 构建后端已切到 uv_build（与 ai4-grlc 的 session_dir 缺陷无关，属构建层修复）。Windows 沙箱下 setuptools editable 重建 egg-info 持续「拒绝访问」，runtime 与 buffer 均切 uv 原生 uv_build 后端（module-name 显式声明 src 包）并加 `-p no:cacheprovider`（pytest 9.2 在 .pytest_cache 写入被拒时 mkdtemp 无限重试挂起）；全量 CI 21/21 阶段、874 用例通过（runtime 106 passed、buffer 30 passed），PR #54 mergeable:true。Linux 侧首次真跑仍待 Gitee Go 接入后在 ci.sh 矩阵确认（脚本已带 no:cacheprovider，与 Windows 行为一致），本票第四条维持等待 grlc 修复。

