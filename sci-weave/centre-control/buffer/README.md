# Buffer

中央服务器上的共享草稿箱。它保存尚未进入任何领域候选分支的原始内容，按命名空间区分审核人，由人完成一审。

## 存什么

- Research Mapping 的路线变更草稿
- LLM-Wiki 的文档与资源引用草稿

Task Agent 的定义与代码留在研究员自己的仓库，不进入草稿箱。

## 不做什么

- 不创建候选分支，不写领域存储，不发起执行
- 不判断科研内容对错
- 不保存候选或正式版本正文
- 不保存执行过程状态；端侧待审的 Execution Submission 留在 Task Agent Gateway 的本地 SQLite

## 存储

TerminusDB，一个库 `sciweave_draft_domain`，两个命名空间：

| 命名空间 | 内容 | 审核人 |
| --- | --- | --- |
| `mapping` | Research Mapping 路线变更草稿 | 任务节点负责人 |
| `wiki` | LLM-Wiki 文档与资源引用草稿 | Wiki 负责人 |

两个命名空间同库，因此按命名空间授权需要在服务层校验，不能只靠库级权限。

## 文档

契约见 [`docs/data-flow/draft-buffer.md`](../../../docs/data-flow/draft-buffer.md)，工单见 `.tickets/ai4-xem8.md`。

本目录是独立项目，尚未实现。
