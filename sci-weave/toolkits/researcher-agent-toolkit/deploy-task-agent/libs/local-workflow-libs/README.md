# 本地工作流目录

放你自己的 Workflow YAML。加载顺序：`libs/workflow-libs/`（出厂）先加载，本目录后加载，**同名定义以本目录为准**。

设置 `LOCAL_WORKFLOW_LIBS_PATH` 指向任何目录都可以；不设时默认就是这里，目录为空或不存在都正常。

写法和出厂示例一致，要点如下：

- 必须写 `version: 1.0.0`；
- agent 写在 `agents:` 段下面，工作流写在 `workflows:` 段下面；
- 本目录内 agent 名与工作流名必须唯一（重名报 `[duplicate_definition]`）；
- 整个目录会被合并成一个命名空间，所以即便只想加一个工作流，其中的 agent 名也不要和出厂示例撞。

协议全文见 [`../workflow-libs/README.md`](../workflow-libs/README.md)。
