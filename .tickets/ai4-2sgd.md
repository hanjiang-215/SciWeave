---
id: ai4-2sgd
status: in_progress
deps: []
links: []
created: 2026-10-20T07:46:16Z
type: chore
priority: 1
assignee: hanjiang
tags: [ticket-index, engineering]
---
# 工单索引自动同步钩子与增量审查

为 ticket-index 增加 diff 子命令：只输出与当前生成文件的 unified diff，不写盘，便于只审查变化。新增 .cursor/hooks/ticket-index-sync.py 与 .cursor/hooks.json：执行 fer 变更命令后、编辑 .tickets/ai4-*.md 或 docs/tickets/index.toml 后自动运行 render。同步更新 ticket-index SKILL.md、docs/agents/issue-tracker.md、.cursor/rules/dev/use_fer.mdc。另将产品与需求、Research Mapping、LLM-Wiki 三个模块的 26 张工单 assignee 统一为 hanjiang。

## Acceptance Criteria

diff 无变化时输出“生成文件已是最新”，有变化时只列出 hunk；render 与 check 退出码 0；钩子对 fer 变更和工单文件编辑触发，对 git status 等无关命令不触发；26 张工单 assignee 为 hanjiang，INDEX 与模块文件同步更新。


## Notes

**2026-10-20T07:49:28Z**

验证（2026-10-20）：py_compile 通过；ticket_index.py render/check 通过（59 张工单、7 个模块）；diff 无变化时输出 生成文件已是最新；钩子脚本直接调用 after-file-edit、after-shell、非 fer 命令均返回 0。Cursor 会话内未观测到钩子自动触发（afterShellExecution 探针无日志），需重启 Cursor 后在 Hooks 面板确认；ticket-index 技能与 diff 增量审查已生效。

**2026-10-20T08:13:07Z**

提交与 PR（2026-10-20）：提交 93ffb44 已推送到 origin/feature/zhanyunfei；Gitee Pull Request #13 https://gitee.com/qi-yueran/ai4science/pulls/13，目标分支 develop。验证：ticket_index.py render/check 通过（59 张工单、7 个模块），py_compile 通过，git diff --check 通过。

**2026-10-20T15:05:09Z**

索引输入路径变更：index.toml 已按 ai4-d4sw 拆分为 docs/tickets/meta/ai4-*.toml 与 docs/tickets/modules.toml，钩子监听的 after-file-edit 路径随之调整；钩子的触发条件不变，仍只对 fer 变更命令与索引输入文件编辑触发 render。
