# SciWeave Centre Agent

本目录是中央服务器上的 Centre Agent（中央 Agent）项目组。Centre Agent 的首版职责是对 Research Mapping 与 LLM-Wiki 的候选进行预审，必要时创建混合候选，并把结果通知给 Project Owner（项目负责人，简称 PO）选择。

本 README 是首版功能范围声明，暂不代表这些能力已经实现。

## 首版能力范围

### 读取正式内容

Centre Agent 通过两套相互独立的领域管理 MCP 读取正式内容：

- Research Mapping 正式内容；
- LLM-Wiki 正式内容。

Centre Agent 不直接连接 SQLite、TerminusDB 或其他领域存储。两个领域的对象、存储和权限保持隔离。

### 读取候选

Centre Agent 可以读取全部可能进入正式化流程的候选，而不是只读取自己或某个研究员提交的候选：

- Mapping 候选列表和候选详情；
- Wiki 候选列表和候选详情；
- 候选固定 head；
- 候选对应的正式基准；
- 来源候选、来源作者和当前治理状态。

实际的领域工具为：

- Mapping：`get_formal_mapping`、`list_candidates`、`list_reviewable_candidates`；
- Wiki：`get_formal_wiki`、`list_wiki_candidates`、`list_reviewable_wiki_candidates`。

这 6 个读工具要求 `centre` 能力名。候选正文由对应领域管理 MCP 提供，Centre Agent 不绕过领域服务读取存储。

### 预审报告

Centre Agent 对两个领域追加预审报告，工具为单个 `append_prereview_log`，带必需的领域参数（`mapping_domain_id` 或 `wiki_domain_id`）：

- Mapping：`append_prereview_log(mapping_domain_id, ...)`；
- Wiki：`append_prereview_log(wiki_domain_id, ...)`。

能力名为 `prereview_log`，与读候选用的 `centre` 分开配置。两个领域走两次独立调用，不共享领域对象或事务。预审报告采用领域治理记录的追加语义，不能修改历史报告。预审是正式化前的硬门禁，但预审结论不等同于 PO 的正式发布决定。

### 创建混合候选

当多个候选需要合并时，Centre Agent 可以创建新的混合候选，工具为单个 `create_merged_candidate`，同样带必需的领域参数：

- Mapping：`create_merged_candidate(mapping_domain_id, ...)`；
- Wiki：`create_merged_candidate(wiki_domain_id, ...)`。

能力名为 `merged_candidate`，与 `prereview_log` 分开配置。新候选必须记录全部来源候选和来源作者。Centre Agent 不修改已有候选；混合候选创建后，来源作者不因此获得对混合候选的操作权。

### 读取注册表

Centre Agent 可以读取注册表中的事实登记信息：

- Centre Agent 和端侧 Agent 的登记记录；
- Project Owner 的稳定标识；
- 用于通知的 PO 联系邮箱或通知联系人记录。

注册表只用于事实留痕和通知目标发现，不参与鉴权。注册表不得保存邮箱密码、SMTP 令牌、API Key、模型凭据或其他秘密。

### 通知 PO

Centre Agent 可以创建结构化的 PO 通知请求：

- `enqueue_project_owner_notification`；
- 通知中引用候选、预审报告、冲突和混合候选的稳定标识；
- 通知告知 PO 下一步需要查看或选择的对象。

实际邮件投递由独立通知组件完成。邮件地址、SMTP 地址、账号和令牌由通知组件通过环境变量配置，Centre Agent 不直接持有邮件凭据。

邮件仅用于提醒，不承载以下事实：

- PO 的正式批准；
- 候选选择结果；
- 正式版本发布；
- 任务交接或执行指令。

邮件投递失败只记录通知失败并支持重试，不撤销已经写入的预审报告或已经创建的候选。

## 明确禁止的能力

Centre Agent 首版不提供以下能力：

- 写入或修改正式 Mapping；
- 写入或修改正式 Wiki；
- 修改已有候选；
- 写草稿箱接纳状态；
- 代替 PO 执行审核、选择或正式化；
- 发起、调度、重试或下发 Task Agent 任务；
- 读取端侧 Agent 的本地执行记录；
- 直接访问领域数据库；
- 通过注册表获得额外权限；
- 使用邮件回复作为治理决定；
- 建立私有审计写入通道。

## 调用和留痕边界

所有能力最终按独立 MCP 工具暴露，并在对外接口层接入中央调用账本。留痕记录调用方、通道、服务、工具、目标、结果和耗时，不复制候选正文、凭据或完整入参。

Centre Agent 不自行定义第二套审计事件，也不直接写领域治理记录以外的私有审计表。

## 当前项目结构

本目录包含四个独立 Python 子项目：

- `gateway/mcp`：常驻 MCP 接入与处置面；
- `gateway/subscriber`：队列订阅器,出站连接消息队列并驱动 Worker；
- `gateway/ingest`：后续迁移为候选事件订阅角色的骨架；
- `worker`：短生命周期 Worker。

中央 Agent 的能力规格见工单「中央 Agent 能力接口收口」和「中央 Agent 候选预审职能地图」。本 README 先定义能力范围,不实现新的 MCP、注册表、通知服务或邮件投递。

## 当前工作区验证

项目组根使用 uv workspace 并维护唯一 `uv.lock`：

```bash
cd sci-weave/centre-control/centre-agents
uv sync
```

现有 Gateway MVP 回归测试：

```bash
uv run --package sciweave-task-agent-gateway-mcp \
  python -m unittest discover -s gateway/mcp/tests -v
```

各角色只从其本地 `.env` 读取配置；仓库只提交 `.env.example`。
