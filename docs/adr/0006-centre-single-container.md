# 中央服务单容器多进程部署

`centre-control` 下的 9 个独立 Python 项目（research-map、research-wiki、buffer、registry、email-service、coordinator、centre-agents 项目组、dashboard-api、web-ui）被打进**一个镜像、一个容器**，容器内用 supervisord 托管 12 个进程角色，部署在中央服务器；端侧套件与 SciencePal 科研核心不在这里。

## Status

accepted（2026-10-27）。裁决了 `centre-control/README.md` 原「每个目录是独立项目，不作为一个部署单元一起启动」的约定与 `docs/TECH_STACK.md` 未确定项里「是否打成一个镜像」的待裁决问题。

## Context

- 2026-10-27 项目审查（`docs/AI4Sci-review-2026-10-27.md`）把「评审期链接可访问」列为赛事硬门槛；`ai4-v869` 需要中央 MCP 端点公开可达。
- 服务器形态已知：一台中央服务器承载全部治理面；端侧执行由 DSH / WorkBuddy / SciencePal 承担，通过 MCP 端口访问中央。
- 此前的 `demo-stack` 是多容器编排（每项目一个镜像），覆盖演示子集，不是生产部署单元。

## Considered Options

1. **沿用多容器：每项目一个镜像 + compose 编排**（否决）。9 个项目 × 各自镜像 = 9 个构建、9 个版本、9 组健康检查；部署体与故障面都更大；与「一台服务器、一套数据卷、一个队列」的实际形态不匹配。另外自己的 `.venv` 与 `uv.lock` 各不相同，各自镜像的版本漂移会很难追。
2. **单镜像 + 单容器 + 多进程（supervisord）**（采纳）。一个构建产物、一个发布单元、一组令牌/凭据环境；进程间共用 `/data` 数据卷与 TerminusDB/Redpanda 连接；`supervisorctl` 提供单角色启停与日志。代价：单容器内进程互相影响（启动顺序、日志混淆），可靠性上限低于进程隔离。
3. **单镜像 + 多容器（同一镜像跑多个服务）**（否决中间态）。进程隔离好一点，但每多一个容器就多一份编排心智；本阶段没有按角色扩缩容需求，不值得。

## Consequences

- `sci-weave/centre-stack/` 成为中央服务的部署单元：`Dockerfile`（多阶段，前端静态构建 + uv 同步 9 项目）、`compose.yaml`、`supervisord.conf`、`.env.example`、`README.md`。
- 第三方服务（TerminusDB、Redpanda）仍按 `sci-weave/service/<服务名>/` 独立部署，本栈经 `host.docker.internal` 引用，不并入单容器（它们是存储/队列底座，不是「中央业务服务」，且已有自己的生命周期与升级路径）。
- 12 个进程角色只能通过 supervisord 重启，不再有每容器独立重启的粒度；单角色更新 = 整镜像重建。
- 数据卷合并为 `/data`：SQLite、会话、审计都落在同一个具名卷，备份单位从「每服务」变为「每容器」。
- 本裁决只约束**部署形态**，不改变 `centre-control` 下各子项目「独立提交 `uv.lock`、不共用锁文件」的代码边界；`shared/` 仍然是代码归属边界。
- worker 角色不常驻，由 gateway 用 multiprocessing 拉起，不进 supervisord 常驻名单。
- 已知取舍：容器内并发写多个审计 SQLite（每服务一份，可合并不强制）、单点故障面扩大、需要部署方配好反代与 TLS（README 已注明）。