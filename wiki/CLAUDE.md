# SciWeave Wiki

<!-- harness-wiki:vault-schema -->

本目录是 AI4Sci/SciWeave 项目的可追溯 Markdown Wiki，使用 Obsidian 兼容的 `[[wikilinks]]`。

## Operations

- 新增事实前先阅读 `wiki/index.md` 和相关 `wiki/sources/` 页面。
- 非显然事实必须引用来源页；实现状态必须区分源码/测试证据与设计声明。
- 文档存在冲突时保留冲突，写入 `## Contradictions`，不得静默覆盖。
- 页面使用 YAML frontmatter：`type`、`created`、`updated`、`sources`、`tags`。
- 文件名使用 kebab-case；维护后更新 `wiki/index.md` 与 `wiki/log.md`。
- 本 Wiki 介绍仓库事实，不保存凭据、`.env`、缓存、日志或构建产物。

## Paired projects

| Project | Path | Purpose | Status |
|---|---|---|---|
| AI4Sci / SciWeave | `../` | 本 Wiki 对应的产品与工程仓库 | building |

<!-- /harness-wiki:vault-schema -->
