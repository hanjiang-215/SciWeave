# TerminusDB 本地验证服务

这个目录提供用于 Research Mapping 版本行为验证的最小 TerminusDB Server 配置。它只提供本地开发验证所需的数据库服务，不包含 SciWeave 应用、科研人员操作界面或业务账号。

科研人员使用 SciWeave 时不需要直接操作 Docker、TerminusDB、branch 或 Commit；这些内容属于开发和审计实现。研究人员的正常工作入口应是项目、任务、证据和审核流程。

## 固定版本和服务边界

- 镜像：`terminusdb/terminusdb-server:v12.0.8`（Docker Hub 上的实际标签带 `v` 前缀，`12.0.8` 不存在）
- 已验证存储组件：TerminusDB Store `0.19.8`
- 本机端口：`6363`
- 本机地址：`http://127.0.0.1:6363`
- 数据卷：`ai4sci-terminusdb-data`
- 用途：验证 Schema、TaskNode、Dependency Edge、Commit、History、Diff、candidate branch 和 rebase 行为
- 限制：TerminusDB 的 Commit、branch 和 rebase 不代表 Project Owner 审核；Proposal 状态、正式版本指针、只读归档和审计事实由平台层管理

TerminusDB 和镜像只用于本地验证。本仓库不重新分发镜像，也不把该配置当作生产部署方案；镜像及其依赖的许可证和使用限制以官方发行说明为准。

## 使用前提

需要安装并启动 Docker Desktop，使 `docker compose version` 可以正常执行。Windows PowerShell、macOS 和 Linux 均可在仓库根目录执行以下命令。

检查 Docker Compose：

```bash
docker compose version
```

## 启动

在仓库根目录执行：

```bash
docker compose -f dockers/service/terminusdb/compose.yaml up -d
```

若本机无法直连 Docker Hub，可先通过可用的镜像代理拉取，再用仓库需要的名字打标签，Compose 配置不需要改动：

```bash
docker pull --platform linux/amd64 <mirror>/terminusdb/terminusdb-server:v12.0.8
docker tag <mirror>/terminusdb/terminusdb-server:v12.0.8 terminusdb/terminusdb-server:v12.0.8
```

注意标签带 `v` 前缀：Docker Hub 上没有 `terminusdb/terminusdb-server:12.0.8`。

查看容器状态：

```bash
docker compose -f dockers/service/terminusdb/compose.yaml ps
```

查看服务日志：

```bash
docker compose -f dockers/service/terminusdb/compose.yaml logs -f terminusdb
```

服务默认映射到本机：

```text
http://127.0.0.1:6363
```

可以先用浏览器访问，或者检查 HTTP 端口：

```bash
curl -i http://127.0.0.1:6363/
```

返回服务响应即表示端口已经可访问。具体 API 路径和初始化行为以 TerminusDB 12.0.8 容器日志及对应版本文档为准。

## 本地验证凭据

历史验证使用了本地容器初始化的 `admin:root` 凭据。该凭据只适用于隔离在 `127.0.0.1` 的临时验证环境，不得用于共享机器、公开网络或生产环境，也不得提交到仓库。

在共享或长期环境中，必须按照 TerminusDB 12.0.8 的官方说明通过本机环境变量或安全凭据管理器设置管理员密码；密码、令牌和 `.env` 文件不得提交。SciWeave 面向研究人员的应用入口不应要求用户直接使用数据库管理员凭据。

## 准备精确 Commit 验证数据

`research-mapping` 的集成测试需要一个包含至少两次提交的数据库：一次作为历史 Commit，另一次作为 branch head。以下步骤在隔离的本机环境执行，数据库名和提交说明可自行替换。

```bash
# 1. 建库
curl -u admin:root -X POST http://127.0.0.1:6363/api/db/admin/sciweave_mapping_it \
  -H 'Content-Type: application/json' \
  -d '{"label":"SciWeave Mapping Integration","comment":"exact commit read verification"}'

# 2. 定义 schema（首次写入前必须存在，否则报 ascribed_type_does_not_exist）
curl -u admin:root -X POST 'http://127.0.0.1:6363/api/document/admin/sciweave_mapping_it?graph_type=schema&author=it&message=define-schema' \
  -H 'Content-Type: application/json' \
  -d '[{"@type":"Class","@id":"TaskNode","@key":{"@type":"Lexical","@fields":["label"]},
        "label":"xsd:string","status":"xsd:string"}]'

# 3. 第一次提交：历史版本
curl -u admin:root -X POST 'http://127.0.0.1:6363/api/document/admin/sciweave_mapping_it?author=it&message=seed-first' \
  -H 'Content-Type: application/json' \
  -d '[{"@type":"TaskNode","@id":"TaskNode/first","label":"first","status":"planned"}]'

# 4. 第二次提交：branch head
curl -u admin:root -X POST 'http://127.0.0.1:6363/api/document/admin/sciweave_mapping_it?author=it&message=seed-second' \
  -H 'Content-Type: application/json' \
  -d '[{"@type":"TaskNode","@id":"TaskNode/second","label":"second","status":"planned"}]'

# 5. 读取提交标识
curl -u admin:root 'http://127.0.0.1:6363/api/log/admin/sciweave_mapping_it/local/branch/main?count=10'
```

`Class` 使用 `Lexical` 键时，`@id` 必须等于按键值生成的 ID（例如 `label` 为 `first` 时是 `TaskNode/first`），否则服务返回 `SubmittedIdDoesNotMatchGeneratedId`。日志每条记录的 `@id` 形如 `ValidCommit/<identifier>`，`identifier` 字段就是提交哈希，`parent` 指向父提交。

## 实测行为（2026-10-21）

- 鉴权：容器默认开启 JWT 但未配置密钥来源，Bearer 令牌一律失败；可用的是 HTTP Basic 的容器存储密钥凭据（默认 `admin:<store-key>`，即 `admin:root`）。匿名访问 `/api/document/...` 返回 403。
- 精确 Commit 读取：`GET /api/document/{store}/{db}/local/commit/{hash}?as_list=true&graph_type=instance` 配合请求头 `TerminusDB-Data-Version: commit:{hash}` 返回 200，响应头回显同一个 `commit:{hash}`，正文只包含该提交时点的文档。
- 未知 Commit：文档路由和日志路由都返回 `500 api:InternalServerError`，不是 404。因此“缺失”无法仅凭 HTTP 状态判定，调用方必须按不可用处理，不能当成空快照。

## 停止和清理

停止容器但保留数据卷：

```bash
docker compose -f dockers/service/terminusdb/compose.yaml down
```

停止容器并删除本次 Compose 创建的数据卷：

```bash
docker compose -f dockers/service/terminusdb/compose.yaml down -v
```

第二条命令会删除 TerminusDB 的本地测试数据，请确认不再需要后再执行。清理数据卷不会改变平台保存的 Proposal、Formal MappingRevision 或 AuditEvent；生产系统不能使用物理删除代替业务上的废弃或审计归档。

## 验证范围

`ai4-9hcj` 和 `ai4-2alw` 已在 TerminusDB 12.0.8、TerminusDB Store 0.19.8 上验证 Schema、TaskNode、DependencyEdge、Commit、History、Diff、candidate branch、rebase 和冲突行为。`ai4-2sdn` 还验证了 branch 不提供 Proposal 状态、只读归档和治理元数据，因此这些规则必须由平台层补充。

`ai4-mqtq` 在 2026-10-21 补上了真实服务上的精确 Commit 读回：按 `commit:<hash>` 读取历史快照，并与 branch head 的快照对比确认两者内容不同。
