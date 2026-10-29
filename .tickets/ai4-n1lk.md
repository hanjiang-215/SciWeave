---
id: ai4-n1lk
status: closed
deps: []
links: []
created: 2026-10-28T15:17:01Z
type: feature
priority: 1
assignee: Frank Qi
tags: [mapping, wiki, bootstrap, initialization]
---
# 启动时为 Mapping 与 Wiki 创建默认正式版本

在 research-map 与 research-wiki 启动初始化阶段，对没有 current formal revision 的领域幂等创建可精确读取的空正式快照、SQLite 正式版本和 current pointer；已有正式版本不得覆盖。验证重启幂等、候选可基于默认版本提交，以及 TerminusDB 写入失败时服务拒绝启动或明确暴露错误。

## Design

启动初始化只在领域没有 current pointer 时执行；空快照必须在 TerminusDB 形成不可变 commit，SQLite 记录正式版本及 current pointer，重复启动返回已有版本。不得把 TerminusDB main head 或空字符串当作基准。

## Acceptance Criteria

map 与 wiki 首次启动创建默认空正式版本；已有正式版本启动不改写；重复启动不产生第二个版本；默认版本可被正式查询并作为 candidate base；TerminusDB/SQLite 失败有明确错误且不留下半成品；两领域测试通过。

## Notes

**2026-10-28**

已实现并验证：

- Mapping 与 Wiki 启动时先检查 current pointer；已有正式版本不触碰 TerminusDB。
- 新领域分别创建可精确读取的 TerminusDB 默认快照：Mapping 为 `[]`，Wiki 为稳定 domain-scoped ID 的空正文 `WikiRevision`。
- SQLite 以 `BEGIN IMMEDIATE` 原子写入正式 revision、succeeded formalization result 和 current pointer；partial/conflict/未知外部写入 fail closed。
- `uv run --cache-dir /tmp/uv-cache --with pytest pytest -q`：research-map 135 passed、5 skipped；research-wiki 145 passed、12 skipped。
- 两领域 `python3 -m compileall -q src tests` 通过。
