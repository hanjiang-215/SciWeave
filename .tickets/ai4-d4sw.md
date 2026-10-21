---
id: ai4-d4sw
status: closed
deps: []
links: []
created: 2026-10-20T15:00:47Z
type: chore
priority: 1
assignee: hanjiang
tags: [ticket-index, engineering]
---
# 工单索引去冲突：元数据入票与生成物不入库

把 docs/tickets/index.toml 拆成 modules.toml（模块注册表）与 docs/tickets/meta/ai4-xxxx.toml（每票 module/summary），消除共享文件的相邻行冲突。INDEX.md 与 modules/*.md 改为本地生成物，加入 .gitignore 并移出版本库，PR 不再携带全局聚合文件。同步更新 ticket-index 脚本、SKILL.md、hooks、issue-tracker.md 和 use_fer.mdc。

## Acceptance Criteria

每张工单有独立 meta 文件；render/check 通过；INDEX.md 与 modules/*.md 不再被 Git 跟踪；hooks 配置不再引用不存在的 probe.py；合并他人 PR 后只需运行 render，不再出现生成文件冲突。


## Notes

**2026-10-20T15:04:10Z**

验证验收标准：78 张工单均有 meta 文件，7 个模块注册；check 输出 OK 且退出码 0；git ls-files docs/tickets 为空，INDEX.md 与 modules/ 已不在版本库；docs/agents/issue-tracker.md、.cursor/rules/dev/use_fer.mdc、.cursor/hooks/ticket-index-sync.py 的 index.toml 旧引用已改为 meta/ 与 modules.toml。
