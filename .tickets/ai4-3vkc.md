---
id: ai4-3vkc
status: open
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

- [ ] 仓库内 `check_iris_input.py` / `run_iris_baseline.py` / `iris_data.csv` / `iris_data_failure_inject.csv` 各只有一份。
- [ ] `sciencpal-onboarding` 的 README 与 SKILL 改为引用 `demo-evidence/` 的路径。
- [ ] 沙箱上传步骤在新的引用下仍然可执行（给出上传后的目标目录结构）。
- [ ] `grep -rn "checks/" humans/competition/` 不再指向已删除的副本。

## Notes

**2026-10-27 登记（Frank Qi）**

身份核对：本票 assignee 为 Frank Qi，当前分支 `feature/frank-qi`、`git config user.name=Frank Qi`，一致。

优先级低于 `ai4-483l` / `ai4-j7g2`：那两票改脚本时必须两份同改，去重完成前以「两份同改」为临时约定。
