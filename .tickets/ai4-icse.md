---
id: ai4-icse
status: open
deps: [ai4-ykti]
links: []
created: 2026-10-29T14:26:45Z
type: feature
priority: 1
assignee: Frank Qi
tags: [toolkit, suitecheck, security, ready-for-agent]
---
# 让 suitecheck 只读校验声明式套件

依据工具包项目级部署与 Harness 导出设计规格，收敛 suitecheck 为跨平台只读验证入口，禁止因清单包含 install/check 字段而执行任意 shell 命令。

## Design

Blocked by 声明式清单与平台能力模型。校验覆盖清单闭合性、引用、能力上限、平台声明、秘密边界、输出路径和配置指导完整性；保留薄入口但不执行任意命令。

## Acceptance Criteria

- [ ] suitecheck check 能验证清单闭合性、引用存在性、能力上限、平台状态、秘密边界、输出路径和配置指导完整性。
- [ ] suitecheck 不执行清单中的任意 shell、PowerShell 或 CMD 命令，未知命令不会获得执行机会。
- [ ] 非法清单、越界能力、缺失资源、秘密内容和路径越界均返回稳定可诊断 finding。
- [ ] 回归测试证明检查过程只读，且不会修改项目、用户配置或服务状态。
- [ ] 两套目标套件及跨套件技能命名冲突在新契约下可验证。
