---
id: ai4-e1jk
status: closed
deps: []
links: []
created: 2026-10-27T15:18:54Z
type: feature
priority: 1
assignee: hanjiang
tags: [deployment, compose, infra, centre-control]
---
# 中央服务单容器部署单元：镜像、compose 与访问路径

现有 compose 只有 sci-weave/demo-stack 的演示子集（research-map 看板来源 + dashboard-api + web-ui 三个容器），没有覆盖 centre-control 的 9 个子项目。用户决定把中央服务全部打进一个镜像、在一个容器内多进程运行，部署到服务器；端侧套件与 SciencePal 科研核心另挂在 dsh/workbuddy。docs/TECH_STACK.md 第 73 行把这项列为待裁决冲突，本票即该裁决的落地。

## Acceptance Criteria

1) 新增部署单元目录，含 Dockerfile、compose.yaml、supervisord 多进程配置、.env.example 与 README；2) 镜像内含 research-map(MCP+看板来源)、research-wiki(MCP+看板来源)、buffer、registry、email-service、coordinator、centre-agents(gateway/mcp+subscriber)、dashboard-api、web-ui 全部角色；3) 除 web-ui 静态资源外不含 dev 依赖与测试产物；4) 全部端口、地址、令牌、路径经环境变量配置，supervisord 用 ENV 插值，不硬编码；5) 第三方 TerminusDB/Redpanda 不重复定义，按既有约定复用 sci-weave/service/<服务名>/；6) README 写明访问路径表（对外端口、健康检查、MCP 端点、看板页面）、起停命令、令牌与凭据要求、容器内进程清单与日志查看方式；7) docker compose config 校验通过，并在容器可构建时做一次真实启动验证；无法构建时如实记录卡点，不声称通过；8) 同步更新 docs/TECH_STACK.md 未确定项与 docs/adr 决策记录，说明这项冲突如何裁决；9) 不提交真实凭据。


## Notes

**2026-10-27T15:31:12Z**

﻿**2026-10-27 交付（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`，三者一致。

新增部署单元 `sci-weave/centre-stack/`：`Dockerfile`（多阶段：node 构建前端 + python 装 9 个 uv 项目，运行时仅 Python + supervisord）、`compose.yaml`、`supervisord.conf`（12 个 program）、`compose.local-redpanda.yaml`（可选覆盖）、`.env.example`、`README.md`、`scripts/serve_web_ui.py`、`scripts/bootstrap_terminusdb.py`、`Dockerfile.dockerignore`。

12 个进程角色：registry、email-service、mapping-mcp、mapping-dashboard、wiki-mcp、wiki-dashboard、draft-buffer、centre-gateway-mcp、centre-gateway-subscriber、coordinator、dashboard-api、web-ui-static。worker 不常驻（gateway 用 multiprocessing 拉起）。

裁决与文档：`docs/adr/0006-centre-single-container.md` 记录「单镜像单容器多进程」裁决与三个备选方案的取舍；`docs/TECH_STACK.md` 未确定项改为密钥管理/CI/Redpanda 生产形态/公网暴露；`sci-weave/centre-control/README.md` 同步说明部署单元。

同期修复（同一票范围）：`research-map` 的 `SCIWEAVE_MAPPING_KAFKA_BOOTSTRAP` 只读进局部变量、未传给 `MappingConfig`，导致 `create_governance_publisher` 恒为 Noop——真实部署里治理事件永不发布。已修并新增 `research-map/tests/test_config.py` 4 项回归。

验证（本机 Docker 29.6.1 / Compose v5.1.4）：

```text
docker compose --env-file .env.example config --quiet   → 0
docker compose build                                     → sciweave/centre:local
docker compose run --rm bootstrap                        → mapping/wiki/buffer 三库 created
容器启动 20s 内 healthy
supervisorctl status                                     → 11 RUNNING / 1 FATAL
   FATAL: centre-gateway-subscriber（无 DEEPSEEK_API_KEY 且未开 passthrough，按设计拒绝启动）
GET :8080/health 200；:8702/health 200；:8710/:8720/:8730/:8740/:8760/:8762/health 200
GET :8750/health 503（SMTP 未配置，状态查询仍可用）
GET :8702/api/dashboard/snapshot → mode=live，gateway=fresh
   mapping/wiki=unavailable（新库无正式版本，正确语义）；queue=unavailable（subscriber 未运行）
research-map 全量 133 passed / 5 skipped（含新增 4 项）
centre-control 矩阵 16/17 阶段、700 passed、22 skipped；唯一失败为 research-map 传输层偶发（重跑全绿）
```

实跑修掉的四个容器专属问题：dockerignore 的 `**/data` 误排除 `web-ui/src/data`；supervisord 程序缺 `stdout_logfile`/`stderr_logfile` 导致日志落进容器 `/tmp`；PowerShell 重写配置文件引入 BOM 使 supervisord 无法解析；全新环境三个领域库不存在导致草稿箱 FATAL、看板来源恒 unavailable（已补幂等引导脚本）。

环境事实（已写进 README，不算代码缺陷）：仓库自带 Redpanda 的 external 监听 advertise 为 `localhost:19092`，容器内不可达，需用 `compose.local-redpanda.yaml` 接入其 docker 网络走 `redpanda:9092`；coordinator 在 broker 短暂不可达时被异常打断并由 supervisord 重启。

未验证：未在 Linux 主机上跑过（只有 Windows + Docker Desktop）；未配置 SMTP 做真实发信；未配 DEEPSEEK_API_KEY 做真实模型执行；公网反代与 TLS 不在本票范围。

遗留（未修，登记为已知缺口）：research-wiki 的 `WikiManagementService` 无治理事件端口，wiki 正式化不产生事件；`centre` 能力只解锁读工具，但 research-map README 与工具 description 文案仍写 "or centre"。
