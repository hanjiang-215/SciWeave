# 注册表

登记中央服务的主体和端侧 Agent。注册是**事实留痕**，不是代码约束：它不阻断调用，也不参与鉴权决定。

## 登记什么

| 对象 | 由谁登记 | 字段 |
| --- | --- | --- |
| 人 | Project Owner | `principal_id`、角色（`researcher` 或 `project_owner`）、通知联系人基本信息 |
| Workflow Agent | 创建者/部署者，创建后 | `agent_id`、`kind`、所属 `principal_id`、`created_by`、Workflow 类型、部署位置描述、登记时间和登记状态 |
| Agent 运行实例 | 部署者，启动或部署后 | `agent_id`、`agent_instance_id`、运行状态、最近心跳或登记时间 |

Registry 不保存 `task_node_id` 集合或“负责哪些节点”的关系。正式任务分配由 Research Mapping 的 `TaskNode.task_owner_id` 和 `TaskNode.executor_refs` 保存；需要反向查询时从正式 Map 派生。

不存密钥、令牌、密码或模型凭据。

## 它不是权限系统

中央服务对端侧的开放面按**能力面**切分，不按主体逐条授权。端侧 Agent 能做什么由它可调用的中央 MCP 工具面决定，不由注册记录决定。理由：Agent 跑在研究员自己的机器上，平台无法强制它做什么，把注册表当成权限系统会给人错误的强制性印象。

当前开放面：

- 端侧 task-agent：读写草稿箱，只能检索到自己提交的内容。
- 研究员：提交 candidate。
- Project Owner：全部中央服务。

一个研究员只能访问自己负责任务的 Agent。

## 文档

契约见 `.tickets/ai4-ujvn.md`。本目录是独立项目，尚未实现。
