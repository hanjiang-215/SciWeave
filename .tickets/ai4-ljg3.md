---
id: ai4-ljg3
status: closed
deps: []
links: []
created: 2026-10-18T12:25:12Z
type: chore
priority: 2
assignee: SciWeave
tags: [dependencies, docs, vibe-coding]
---
# 归一化开发依赖文档为唯一事实来源

将 docs/DEPENDENCIES.md 定位为开发环境与 vibe coding 工具依赖清单，不作为产品技术选型结论；移除 humans/dev/DEPENDENCIES.md 副本并更新规则和仓库内引用。

## Acceptance Criteria

docs/DEPENDENCIES.md 明确区分开发工具、本地验证服务、仓库清单中实际声明的包与未决产品技术选型；删除 humans/dev/DEPENDENCIES.md；更新文件规范，取消该副本同步规则；仓库有效文档和规则中不再引用被删副本；运行引用检查和 git diff --check。


## Notes

**2026-10-18T12:34:20Z**

实现与验证完成（2026-10-18）：docs/DEPENDENCIES.md 已改为开发环境/vibe coding 依赖记录，说明 Node.js + pnpm 及 @codemeall/harness-wiki 仅为仓库环境/清单现状，产品技术架构仍未决；移除 humans/dev/DEPENDENCIES.md，更新文件规范。旧工单的双份同步内容保留为历史事实，并追加说明该做法已由本工单取代。验证：在 .cursor/、docs/ 及非历史票据内容中未发现已删除文件的有效引用；目标文档中未发现此前‘已确定应用技术栈’结论；删除路径不存在；git diff --check 通过。develop 已是当前分支祖先。
