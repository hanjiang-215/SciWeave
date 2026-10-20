# 工单模块：工程基础设施

> 由 `ticket-index` 技能生成，请勿手工编辑。总览：[索引](../INDEX.md) · 归属与简介：[index.toml](../index.toml)

**范围**：依赖与工具链、技术栈与目录规范、本地服务与版本固定

**统计**：共 7 张 · 活跃 1（open 0 / in_progress 1） · 已关闭 6 · 地图 0

## 工单层级

- [ai4-2sgd](../../../.tickets/ai4-2sgd.md) **工单索引自动同步钩子与增量审查** — 为工单索引增加自动同步钩子和只读 diff，并统一产品、Mapping、Wiki 的负责人 `chore` `P1` `in_progress` `hanjiang`
- [ai4-emsk](../../../.tickets/ai4-emsk.md) **Redpanda 本地开发服务 Compose 部署** — 提供可重复启动的单节点 Redpanda Compose，作为本地消息协作验证基础设施 `task` `P1` `closed` `qiyueran`
- [ai4-w333](../../../.tickets/ai4-w333.md) **统一 SciWeave 子项目技术栈与目录规范** — 统一 Python/Vue 技术栈、子项目目录、环境变量配置和规则适用范围 `chore` `P1` `closed` `Frank Qi`
- [ai4-5j2j](../../../.tickets/ai4-5j2j.md) **固定 TerminusDB 验证服务版本并同步说明** — 把 TerminusDB 与 Store 镜像从 latest 固定到已验证版本并同步依赖文档 `task` `P2` `closed` `SciWeave` · 上级 [ai4-ru15](../../../.tickets/ai4-ru15.md)（产品与需求）
- [ai4-5vru](../../../.tickets/ai4-5vru.md) **盘点并补齐项目依赖** — 盘点运行时、开发工具、外部服务和文档依赖，补齐包管理清单与验证命令 `task` `P2` `closed` `SciWeave`
  - [ai4-wzdh](../../../.tickets/ai4-wzdh.md) **补齐本机缺失的三个开发工具（git-cliff / fer / gitee）** — 安装并验证 git-cliff、fer、gitee 三个缺失工具，使规范动作可执行 `task` `P2` `closed` `SciWeave`
- [ai4-ljg3](../../../.tickets/ai4-ljg3.md) **归一化开发依赖文档为唯一事实来源** — 把 docs/DEPENDENCIES.md 定为开发工具依赖的唯一事实来源并清理副本 `chore` `P2` `closed` `SciWeave`
