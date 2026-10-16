# TerminusDB 本地验证服务

这个目录提供用于 Mapping 版本行为验证的最小 TerminusDB Server 配置。它只配置容器、端口和持久化数据卷，不包含账号密码或平台业务服务。

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

可以先用浏览器访问，或者用以下命令检查端口是否可访问：

```bash
curl -i http://127.0.0.1:6363/
```

TerminusDB 的具体 API 路径、初始化方式和认证行为请以容器日志及对应版本文档为准，不要在本配置中提交真实凭据。

## 停止和清理

停止容器但保留数据卷：

```bash
docker compose -f dockers/service/terminusdb/compose.yaml down
```

停止容器并删除本次 Compose 创建的数据卷：

```bash
docker compose -f dockers/service/terminusdb/compose.yaml down -v
```

第二条命令会删除 TerminusDB 的本地测试数据，请确认不再需要后再执行。

## 版本说明

当前使用 `terminusdb/terminusdb-server:latest` 便于第一次验证。完成验证后，应根据实际测试结果将镜像改为明确版本 tag，并把版本、来源、许可证、安装命令和验证结果回写到 `ai4-9hcj` 原型验证任务。
