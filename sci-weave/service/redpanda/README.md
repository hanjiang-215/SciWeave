# Redpanda 本地开发服务

这个目录提供单节点 Redpanda 服务，用于本地验证消息队列协作、上游收集器和外围消息监听服务。它只提供本地开发基础设施，不包含业务消息载荷、应用消费者、生产高可用配置或服务自动恢复逻辑。

## 固定版本和服务边界

- 镜像：`redpandadata/redpanda:v24.3.7`
- 节点：单节点，使用 1 个 CPU 线程和 1 GiB 内存上限
- Kafka API：本机 `localhost:19092`
- Schema Registry：本机 `http://127.0.0.1:18081`
- Pandaproxy：本机 `http://127.0.0.1:18082`
- Admin API：本机 `http://127.0.0.1:19644`
- Docker Compose 网络内 Kafka 地址：`redpanda:9092`
- 数据卷：`ai4sci-redpanda-data`

Compose 仅用于本地开发和验证，不是生产部署方案。单节点配置不提供故障转移、数据副本或生产级资源隔离；业务消息的主题、分区、消费者组、重试和确认语义由平台实现另行定义。

## 使用前提

需要安装并启动 Docker，使以下命令可用：

```bash
docker compose version
```

## 配置校验

只检查 Compose 配置，不构建或启动容器：

```bash
docker compose -f sci-weave/centre-control/redpanda/compose.yaml config
```

## 启动

在仓库根目录执行：

```bash
docker compose -f sci-weave/centre-control/redpanda/compose.yaml up -d
```

查看服务状态和日志：

```bash
docker compose -f sci-weave/centre-control/redpanda/compose.yaml ps
docker compose -f sci-weave/centre-control/redpanda/compose.yaml logs -f redpanda
```

验证管理接口是否可访问：

```bash
curl -i http://127.0.0.1:19644/v1/status/ready
```

停止服务但保留数据卷：

```bash
docker compose -f sci-weave/centre-control/redpanda/compose.yaml down
```

停止服务并删除本地数据卷：

```bash
docker compose -f sci-weave/centre-control/redpanda/compose.yaml down -v
```

`down -v` 会删除本地 Redpanda 数据，请确认不再需要测试数据后再执行。

## 凭据和网络限制

本配置没有提交用户名、密码、令牌或 `.env` 文件。Redpanda 开发镜像默认不配置认证，端口只适合绑定在本机进行隔离验证，不应直接暴露到共享网络或生产环境。

如果后续需要启用 SASL、TLS、ACL 或远程访问，必须先在 fer 工单中明确凭据管理、网络边界和验证标准；真实凭据只能通过本机环境变量、安全凭据管理器或部署平台注入，不能写入仓库。

## 验证范围

本服务用于验证 Redpanda 容器能否作为本地消息队列基础设施运行。它不替代平台侧的消息持久化事实、消费确认、失败分类、重试决策、审计记录或 Web 看板状态判断。
