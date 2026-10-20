---
id: ai4-mqtq
status: open
deps: []
links: []
created: 2026-10-20T08:32:17Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-6ljq
tags: [mapping, implementation]
---
# Mapping 正式版本查询纵向实现

在已选定并记录的 Research Mapping Python 子项目中实现正式版本的读取路径。普通查询从 SQLite 当前正式版本指针和正式治理记录确定唯一已激活 Formal MappingRevision，再读取该版本精确引用的 TerminusDB Commit；不读取 proposal/candidate，也不在不一致时静默回退。

## Design

遵循 Research Mapping 已确定的 SQLite 治理记录权威与 TerminusDB 精确图快照规则。复用已关闭的字段模型、候选治理和跨存储正式化规格；不新增 SDK 假设。若实现需要额外运行时依赖，先建立专门 fer 依赖任务，再声明来源、版本约束、用途、许可证/限制、验证方式及锁文件。

## Acceptance Criteria

- [ ] 正常读取只返回 SQLite 指针确认的正式版本及其精确 TerminusDB Commit 图内容。
- [ ] 候选、未批准或未激活版本不能从普通查询路径返回。
- [ ] 无正式版本、SQLite/TerminusDB 指向不匹配、精确 Commit 不可读等情况均有明确且可测试的结果；不返回候选、不静默回退。
- [ ] 使用临时 SQLite 数据验证单元测试；Termin​​usDB 行为使用仓库已固定的本地验证服务进行最小集成验证，或在服务不可用时提供隔离的测试替身并注明限制。
- [ ] 记录实际部署子项目位置及运行/测试命令；路径和服务地址由环境配置，不依赖固定部署端口。
