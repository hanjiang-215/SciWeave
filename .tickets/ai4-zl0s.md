---
id: ai4-zl0s
status: open
deps: [ai4-lewg, ai4-ykti]
links: []
created: 2026-10-29T14:26:45Z
type: feature
priority: 1
assignee: Frank Qi
tags: [toolkit, harness-export, ready-for-agent]
---
# 实现跨平台 Harness 导出器与稳定输出目录

依据工具包项目级部署与 Harness 导出设计规格，将声明式套件导出为 Harness 可发现的自包含输入目录和稳定 manifest。Harness 自己负责注册，不写入 Harness 私有配置。

## Design

Blocked by 项目布局与清单模型。导出器作为跨平台 Python 公共实现，薄 shell/PowerShell/CMD 入口不得重写核心逻辑；具体 manifest schema 与原子替换恢复策略在实现中记录。

## Acceptance Criteria

- [ ] Harness 提供项目根时，输出稳定落在项目 .sciweave/harness/<suite-id>/；未提供且用户未指定时停止并给出明确错误。
- [ ] 输出自包含并包含声明式清单、manifest、Skills、MCP 卡片和配置指导所需输入，不依赖源码 checkout 或绝对路径。
- [ ] 重复导出原子刷新生成目录，不能覆盖 project、data、.env 或生成目录外未知文件。
- [ ] 导出器不读取、复制、打印真实凭据或 .env 值；测试覆盖 token、密码和路径泄露。
- [ ] Harness 可获得唯一输入目录路径，并能从 manifest 列出输入项、版本、能力和配置要求。
