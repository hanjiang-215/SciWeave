---
id: ai4-5j2j
status: closed
deps: [ai4-9hcj]
links: []
created: 2026-10-17T15:21:48Z
type: task
priority: 2
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:task, terminusdb, reproducibility, dependencies, ai4science]
---
# 固定 TerminusDB 验证服务版本并同步说明

根据 `ai4-9hcj` 已验证的 TerminusDB 12.0.8 与 TerminusDB Store 0.19.8，将本地 Compose 从 `latest` 改为可复现的明确镜像版本，并同步服务说明、权威依赖清单和面向人的依赖副本。此任务只处理实现准备与文档一致性，不把 TerminusDB 选择伪装成已确定的正式产品架构。

## Design

固定镜像使用 `terminusdb/terminusdb-server:12.0.8`，保留本地端口 `6363`、数据卷 `ai4sci-terminusdb-data` 和现有启动/停止命令。README 将明确：

- Docker Desktop 和 Docker Compose 是本地验证前置条件；
- 该服务只用于开发验证，不是研究人员的直接工作入口；
- TerminusDB Store 验证版本为 0.19.8；
- 历史验证使用的 `admin:root` 仅限隔离的 localhost 临时环境；
- 共享或生产环境必须通过安全方式设置凭据，不提交密码或令牌；
- Commit、branch、rebase 不代表 Project Owner 审核，Proposal、Formal MappingRevision 和 AuditEvent 由平台层维护。

权威依赖文档先记录版本、来源、用途、验证范围和使用限制，再同步 `humans/dev/DEPENDENCIES.md`。不新增业务代码、运行时依赖或未确认的外部服务。

## Verification

- `compose.yaml` 使用固定镜像 `terminusdb/terminusdb-server:12.0.8`，不再使用 `latest`。
- README 记录版本、Store 版本、端口、数据卷、启动/停止、健康检查、凭据和生产限制。
- 两份依赖清单均记录 TerminusDB Server 12.0.8、TerminusDB Store 0.19.8、Docker Compose 前置条件、来源和验证命令。
- `ai4-9hcj` 的历史验证结果与当前服务配置一致；验证数据仍只使用临时数据库，真实凭据不写入仓库。

## Acceptance Criteria

- [x] `compose.yaml` 不再使用 `latest`，固定到已验证的 TerminusDB Server 12.0.8。
- [x] README 明确 Docker 前置条件、固定版本、TerminusDB Store 0.19.8、端口、数据卷、启动/停止、验证和凭据要求。
- [x] `docs/DEPENDENCIES.md` 记录 TerminusDB 版本、来源、用途、许可证或使用限制、安装/验证命令。
- [x] `humans/dev/DEPENDENCIES.md` 与权威文档保持一致。
- [x] 回写 `ai4-9hcj` 的验证事实：固定版本只复现已验证行为，不代表数据库层自动提供治理审批。
- [x] `git diff --check` 通过。
- [x] 未新增业务代码或未确认运行时依赖。

## Answer

TerminusDB 本地验证服务已固定为 `terminusdb/terminusdb-server:12.0.8`，并同步记录已验证的 TerminusDB Store 0.19.8。该服务只承担 Research Mapping 存储行为验证；科研人员通过 SciWeave 的任务、证据和审核入口工作，不直接接触数据库管理员操作。

## Review conclusion (2026-10-18)

固定版本、服务说明、权威依赖清单和面向人的依赖副本已经互相一致；本票据只提供可复现的开发验证前提，不把 TerminusDB 变成科研人员入口，也不把 branch、Commit 或 rebase 当作业务审批。

## Notes

**2026-10-18T12:33:43Z**

后续说明（2026-10-18）：本工单记录的依赖副本同步是当时完成工作的历史事实；该维护方式现由 ai4-ljg3 的单一事实来源决定取代。当前依赖与开发环境信息统一查阅 docs/DEPENDENCIES.md。
