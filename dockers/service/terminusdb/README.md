# TerminusDB 本地验证服务

这个目录提供用于 Research Mapping 版本行为验证的最小 TerminusDB Server 配置。它只提供本地开发验证所需的数据库服务，不包含 SciWeave 应用、科研人员操作界面或业务账号。

科研人员使用 SciWeave 时不需要直接操作 Docker、TerminusDB、branch 或 Commit；这些内容属于开发和审计实现。研究人员的正常工作入口应是项目、任务、证据和审核流程。

## 固定版本和服务边界

- 镜像：`terminusdb/terminusdb-server:12.0.8`
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
