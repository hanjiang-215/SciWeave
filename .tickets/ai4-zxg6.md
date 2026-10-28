---
id: ai4-zxg6
status: closed
deps: []
links: [ai4-za77, ai4-3qiv, ai4-u9gj, ai4-xem8, ai4-fm4a]
created: 2026-10-28T00:52:00Z
type: bug
priority: 1
assignee: Frank Qi
tags: [toolkit, task-agent, config, correctness]
---
# Task Agent 运行时不加载技能，且草稿字段名与草稿箱 schema 不一致

两个都是「测试全绿、装出来是错的」那一类，合在一张票里因为它们在同一个文件里相邻：
`deploy-task-agent/runtime/src/work_agent_runtime/`。

## 一、`skills=` 从来没传过，技能只是文档

`fast_agent.Agent(..., skills=...)` 是唯一能把 `SKILL.md` 装进模型上下文的地方。运行时从没传过它，
于是 agent 配置留着 `SKILLS_DEFAULT` 哨兵——`fast_agent` 会自己去扫 `~/.fast-agent/skills`。
后果有两层：

1. 套件里的技能一个都没加载，写了一堆 `SKILL.md` 等于没写；
2. 更糟的是它**不是空的**——一个跑在研究员机器上的无人值守 worker，会捡起家目录里恰好在
   那里的任何技能。

`docs/superpowers/specs/2026-10-23-agent-suite-boundary-design.md` 明确禁止运行时自动发现
技能，所以「不传」不是保守，是违约。

## 二、草稿字段名写成了 `source_target_node_id`

中央草稿箱的 `create_draft` 签名用的名字是 `source_task_node_id`
（`centre-control/buffer/src/draft_buffer/service.py:24`，`store.py` 的 `Draft` 类定义，
以及 `main.py:77` 的 `properties`）。端侧 `draft_writer.py` 发的是 `source_target_node_id`。

后果比「字段丢了」严重：`call_tool` 是把 `arguments` 直接 `handler(**arguments)` 展开的
（`src/draft_buffer/__init__.py:25`），多出来的关键字会抛 `TypeError`，被 `main.py` 兜成
`invalid_arguments`。所以**不是丢字段，是整次 `create_draft` 被拒**——每一次草稿写入都失败，
端侧收到的是 `draft_submission_failed`。

端侧测试看不出来：`test_draft_writer.py` 用的是自己写的假 buffer（`_RecordingBuffer`），
它只记录收到的 `arguments`，从不校验字段名。那个假服务里甚至断言了
`call["source_target_node_id"] == "node-1"`，把错误的名字钉成了期望值。

## Acceptance Criteria

- [x] 运行时有 `skills.py`：显式解析两个变量，声明了但不可用就启动失败
- [x] 未声明不等于自动发现：`SCIWEAVE_SKILLS_PATH` 与 `LOCAL_SKILLS_PATH` 都为空时传 `skills=None`
- [x] 套件自己的 `deploy-task-agent-skills/` **不**作为兜底（那是给研究员个人 Agent 的部署说明）
- [x] 草稿字段改用 `source_task_node_id`
- [x] 变量在 `.env.example` 里有注释说明默认空
- [x] 测试覆盖：未声明、目录不存在、指向技能目录本身、空目录、重复目录

## Notes

**2026-10-28T00:55:00Z**

`skills.py` 的三条判定，分别是三种不同的错法：

| 情形 | 结果 |
| --- | --- |
| 变量未设 | 合法：worker 不带技能运行 |
| 变量设了但目录不存在 / 不是目录 / 里面没有 `<子目录>/SKILL.md` | `SkillsConfigError`，启动失败 |
| 变量指向的是技能目录本身（`.../some-skill`，下面就是 `SKILL.md`） | `skills_directory_is_a_skill` |

最后一条是这堆错误里最常见的一个：把 `SCIWEAVE_SKILLS_PATH` 指到某个技能目录，
`fast-agent` 会在它下面找 `<child>/SKILL.md`，找到零个，然后**不报错**。

`skills=None` 是显式传的，不是省略参数——省略等于把选择权交回给 `fast-agent` 的
`SKILLS_DEFAULT`，而那正是要避免的。

验证：`cd sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/runtime && uv run python -m unittest discover -s tests -q`
→ 370 passed（含新增 `tests/test_skills.py` 的 12 个用例）。
另修了 `tests/test_domain_card_permissions.py`：`create_merge_request` 是新增的 Owner 侧工具
（`ai4-8yk5`），必须归入 `OWNER_SIDE`，否则那条「每个服务工具都要被分类」的断言会红。
