---
name: ticket-index
description: 维护 docs/tickets 下的分层工单索引（总览、模块归属、一句话简介、跨模块关系、前沿与阻塞清单）。新增/关闭/改派/依赖/关联 fer 工单之后，或需要盘点、审查、按模块定位工单时使用；也用于回答“当前有哪些工单、谁负责、哪些可以开工”。
---

# Ticket Index

`.tickets/` 里的工单是事实源，但逐张读取成本高。本技能维护一份**派生索引**：总览（`docs/tickets/INDEX.md`）→ 模块（`docs/tickets/modules/<module>.md`）→ 工单行。读取者先看索引定位候选，再打开唯一的工单全文。

索引由脚本渲染。人只维护 `docs/tickets/index.toml` 里的**归属与简介**；状态、类型、负责人、依赖、层级、跨模块关系和计数全部从工单 frontmatter 推导。因此索引不会因手工同步而漂移。

## 何时运行

- 每次新增、关闭、改派、改状态、改依赖或关联工单之后。钩子会自动渲染，但**新增工单仍需补 `index.toml` 条目**并跑 `check`。
- 提交 PR 前，或审查者要求盘点工单时。
- 工单范围变化、需要调整模块归属时。

只读工单、不做工单归属裁决时，直接读现有索引即可，不必运行脚本。

## 自动同步与增量审查

`.cursor/hooks.json` 注册了 `.cursor/hooks/ticket-index-sync.py`：

- `afterShellExecution`：命令里出现 `fer` 的变更子命令时自动运行 `render`；
- `afterFileEdit`：编辑 `.tickets/ai4-*.md` 或 `docs/tickets/index.toml` 后自动运行 `render`。

钩子只保证生成文件不过期，不替人判断模块归属和简介。新增工单时仍在同一轮补 `index.toml`；自动渲染因缺条目失败时，按 `check` 的输出补齐再重跑。新建 `hooks.json` 后需要 Cursor 在会话启动时加载，首次配置或修改后重启 Cursor，并在 Hooks 输出面板确认已触发。

审查只看变化的部分，不要通读整份索引：

```bash
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py diff
```

`diff` 按文件输出 unified diff 且不写盘。只审查输出的 hunk；输出“生成文件已是最新”时直接跳过。

## 工作流

### 1. 检查

```bash
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py check
```

输出缺失归属、缺失简介、未知模块、失效引用（依赖/关联/上级指向不存在的工单）和过期生成文件。先把**错误**处理完，再进入下一步。

需要人工判断归属时，用 `facts` 看紧凑事实表：

```bash
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py facts
```

### 2. 补归属与简介

编辑 `docs/tickets/index.toml`：

- 新工单：在 `[tickets]` 加一行，`module` 写主模块，`summary` 写一句话，例如 `ai4-xxxx = { module = "gateway", summary = "…" }`。
- 跨模块：`module = ["主模块", "次模块"]`，主模块排第一。
- 删除已不存在的工单条目；模块增删改 `[[modules]]`。

简介规则：

- 20–60 个汉字，一行说完“这张票产出或决定了什么”。
- 补充标题没有的信息，不复述标题，不写“本票”“该工单”。
- 研究/验证票写验证对象和用途；地图写目的地；已关闭决策票写结论范围，不抄答案。
- 不写状态、负责人、日期、文件路径；这些由脚本渲染。

完成条件：每张工单恰好有一个条目，且 `summary` 非空。

### 3. 审查变化并写入

先看本轮会改什么，只审查出现的 hunk：

```bash
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py diff
```

确认无误后再写盘。`render` 只写内容有变化的文件：

```bash
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py render
```

审查要点：

- 新工单是否落在正确模块；
- 层级是否跟随 `parent`，跨模块的上级是否标成根节点并带“上级”指针；
- 多模块归属是否只在主模块展开，其他模块只出现引用；
- 前沿、阻塞、待补负责人三张清单是否符合预期。

生成文件带“请勿手工编辑”标记。要改内容就改 `index.toml` 后重跑。

### 4. 验证

```bash
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py check
```

退出码 `0` 且输出 `OK` 即完成。提交时把 `index.toml` 与所有生成文件一起提交。

## 模块归属

主模块是工单**结论最终落地的领域**，不是发起讨论的人、讨论阶段或工单类型。

- 一张票只在一个模块展开；`module` 数组里的其余模块只在“跨模块归属”中引用，不重复展开。
- `parent` 跨模块时，子票在自身模块作为根节点展开，并在行尾标注上级；不把父票复制过去。
- `deps` / `links` 跨模块由脚本汇总到 INDEX 的跨模块关系表；工单行只显示仍阻塞的依赖。
- 新领域出现时，在 `[[modules]]` 增加模块，不要塞进最接近的旧模块。
- 汇总分支（Wayfinder 的 branch/epic）是工单层级，不是模块；模块按领域划分。

### 跨模块的三种写法

| 情况 | 写法 |
| --- | --- |
| 工单本身服务多个领域 | `module = ["主模块", "次模块", ...]`，主模块展开，其余模块引用 |
| 父票在别的模块 | 子票留在自身模块做根节点，行尾渲染 `上级 ai4-xxx（模块名）` |
| 依赖或关联到别的模块 | 不改归属；脚本在 INDEX 生成跨模块关系表 |

不要为了“看起来完整”把同一张票复制到多个模块。重复行会产生两份可能不一致的简介，审查时无法判断哪份为准。

## 输出结构

- `INDEX.md`：用途与读法、状态/类型统计、模块导航、当前前沿（依赖已满足的活跃工单）、阻塞中、待补负责人、跨模块关系、维护约定。
- `modules/<module>.md`：模块范围、统计、按 `parent` 展开的层状工单树、跨模块归属引用。

事实字段（`status`、`type`、`assignee`、`priority`、`deps`、`links`、`tags`、`created`）一律从 `.tickets/*.md` frontmatter 读取。索引不缓存可由工单推导的事实。

## 常见错误

- 在生成文件里改状态：`check` 会报过期，`render` 会覆盖。改工单用 `fer`。
- 新工单漏了 `summary`：`render` 拒绝输出，避免索引出现空简介。
- 把 `SciWeave` 当作负责人：它是团队占位名；INDEX 的“待补负责人”会列出仍活跃的此类工单。
- 用 `links` 代替 `parent` 表达层级：层级只认 `parent`，`links` 渲染为跨模块关系。
