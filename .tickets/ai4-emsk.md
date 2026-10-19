---
id: ai4-emsk
status: open
deps: []
links: []
created: 2026-10-19T06:25:18Z
type: task
priority: 1
assignee: qiyueran
tags: [infrastructure, redpanda]
---
# Redpanda 本地开发服务 Compose 部署

为本地消息队列协作验证提供一个可重复启动的单节点 Redpanda Docker Compose 服务。范围限于本地开发基础设施，不定义业务消息载荷、生产高可用或应用接入代码。

## Design

固定 Redpanda 镜像版本；提供 Kafka API、管理 API 和 Schema Registry 的本机端口；使用命名卷持久化数据；不提交凭据或环境文件；README 说明用途、启动、端口、数据卷和凭据边界。

## Acceptance Criteria

dockers/service/redpanda/compose.yaml 可由 Docker Compose 配置校验通过；README.md 说明用途、启动方式、端口占用、数据卷和凭据要求；服务使用固定镜像版本且不开放外部网络凭据；完成最小配置验证并记录提交。


## Notes

**2026-10-19T06:28:56Z**

实现事实：新增 dockers/service/redpanda/compose.yaml 和 README.md，固定镜像 redpandadata/redpanda:v24.3.7，提供 Kafka API、Schema Registry、Pandaproxy、Admin API 本机端口，并使用命名卷 ai4sci-redpanda-data。验证命令：docker compose -f dockers/service/redpanda/compose.yaml config，退出码 0。按要求未执行 docker compose build、up、镜像拉取或容器启动。待提交。
