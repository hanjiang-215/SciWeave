---
id: ai4-3vkc
status: closed
deps: []
links: []
created: 2026-10-27T01:01:48Z
type: chore
priority: 3
assignee: Frank Qi
parent: ai4-aaff
tags: [chore, demo, evidence]
---
# T1/T2 演示脚本存在两份相同副本，改为单一来源

同一套演示脚本在仓库里存在两份逐字节相同的副本：

| 文件 | sha256（前 16 位） |
| --- | --- |
| `demo-evidence/check_iris_input.py` | `6674f2dfa9fb4188` |
| `sciencpal-onboarding/checks/check_iris_input.py` | `6674f2dfa9fb4188` |
| `demo-evidence/run_iris_baseline.py` | `9d3e0a6ff71a52f9` |
| `sciencpal-onboarding/checks/run_iris_baseline.py` | `9d3e0a6ff71a52f9` |

`iris_data.csv` 与 `iris_data_failure_inject.csv` 同样各有两份。`demo-evidence/` 是「证据与运行入口」，`sciencpal-onboarding/checks/` 是「上传沙箱用的副本」，两者定位不同但内容必须一致。

风险：演示当天如果只改了其中一份（`ai4-483l` / `ai4-j7g2` 就要改这两个脚本），沙箱里跑的仍是旧逻辑 —— 现场表现为「本机 T1 通过，SciencePal 里 T1 失败」，排查成本极高且发生在演示过程中。

## Design

1. 保留 `demo-evidence/` 为唯一来源（它是证据卡的引用目标，也是本机实跑的入口）。
2. 删除 `sciencpal-onboarding/checks/` 下的四份副本，改为在 `sciencpal-onboarding/README.md` 第 0 步与 `skills/minimal-probe/SKILL.md` 里指向 `humans/competition/demo-evidence/` 的同名文件，并说明上传沙箱时按扁平目录放置。
3. 若平台确实要求脚本与数据同目录（见 `minimal-probe/SKILL.md` 第 25 行的 `python checks/check_iris_input.py checks/iris_data.csv`），则改为在打包时复制，而不是在仓库里长期维护两份。
4. 需要同步改的引用点共三处：`sciencpal-onboarding/README.md:21-22`、`sciencpal-onboarding/README.md:30`、`sciencpal-onboarding/skills/minimal-probe/SKILL.md:22-25`。

## Acceptance Criteria

- [x] 仓库内 `check_iris_input.py` / `run_iris_baseline.py` / `iris_data.csv` / `iris_data_failure_inject.csv` 各只有一份。
- [x] `sciencpal-onboarding` 的 README 与 SKILL 改为引用 `demo-evidence/` 的路径。
- [x] 沙箱上传步骤在新的引用下仍然可执行（给出上传后的目标目录结构）。
- [x] `grep -rn "checks/" humans/competition/` 不再指向已删除的副本。

## Notes

**2026-10-27 登记（Frank Qi）**

身份核对：本票 assignee 为 Frank Qi，当前分支 `feature/frank-qi`、`git config user.name=Frank Qi`，一致。

优先级低于 `ai4-483l` / `ai4-j7g2`：那两票改脚本时必须两份同改，去重完成前以「两份同改」为临时约定。

**2026-10-27 实现与验证（Frank Qi）**

提交：`bbac3e9`（删除副本 + 重指向）、`f556dba`（补上传后的目标目录结构）。

验证：

```text
$ find humans/competition -name "check_iris_input.py" -o -name "run_iris_baseline.py" \
      -o -name "iris_data.csv" -o -name "iris_data_failure_inject.csv"
humans/competition/demo-evidence/check_iris_input.py
humans/competition/demo-evidence/iris_data.csv
humans/competition/demo-evidence/iris_data_failure_inject.csv
humans/competition/demo-evidence/run_iris_baseline.py        # 各一份

$ grep -rn "checks/" humans/competition/
（仅剩两条说明性文字，无任何活引用）
```

**执行顺序按票里的临时约定走了**：先按 `ai4-483l` / `ai4-j7g2` 两份同改（`5fe4810`、`c514752` 时两份 sha256 分别相同），确认两份一致后才在 `bbac3e9` 整体删除。这样任何单个提交检出都是自洽的，不会出现「本机通过、沙箱跑旧逻辑」的中间态。

**上传后目录结构**如实写在 `skills/minimal-probe/SKILL.md`：

```text
<沙箱工作目录>/
├── check_iris_input.py
└── iris_data.csv
```

同时说明：脚本对漏传文件现在返回 `reason_code: unreadable_input` 的结构化失败，看到 traceback 说明上传结构不对。

**遗留**：`demo-evidence/README.md:60` 明确写了「两个脚本各自持有一份 `sha256_of`，必须同步修改」，并指出本票合并的是 `demo-evidence/` 与 `checks/` 之间的副本、与这两个脚本无关——避免后人误以为存在某张票会自动合并它们。评审曾建议把 `sha256_of` 抽成共享模块，未采纳：两个脚本都要能作为单文件单独上传到沙箱扁平目录，多一个依赖文件就破坏这一点。改用一致性测试兜底（见 `ai4-483l`）。
