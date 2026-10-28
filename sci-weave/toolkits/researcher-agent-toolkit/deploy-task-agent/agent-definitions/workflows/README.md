# Workflow YAML 指针

工作流声明只有一份，位于 [`../../libs/workflow-libs/`](../../libs/workflow-libs/)。

这个目录原先还存着四份与 `libs/workflow-libs/` 逐字节相同的示例。两份内容相同意味着「改哪份生效」取决于读者读的是 README 还是目录，因此已收敛为一份。这里不放软链：套件要能打成 zip 发给别人的 Agent，软链解压后会坏。

新增或修改工作流请直接编辑 `libs/workflow-libs/`，协议见该目录的 `README.md` 与 `agent-definitions/schema.yaml`。
