---
id: ai4-san9
status: closed
deps: []
links: []
created: 2026-10-22T15:03:47Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-6v70
tags: [web-ui, vue, frontend, read-only]
---
# 实现 Web 看板 Vue 前端与统一快照查询层

在 `sci-weave/centre-control/web-ui` 建立独立 Vue 子项目，以统一只读 `DashboardSnapshot` 为展示边界，提供项目总览、Research Mapping 路线、Wiki 候选、TaskNode 详情、执行与服务状态页面。支持本地演示数据及可替换的只读 HTTP 查询适配器；不执行领域写入、消息补发或自动处置。

## Design

采用 Vue 3.5、Vite 7、TypeScript 5、Vue Router 4、Pinia 3、Vitest 3、Vue Test Utils、jsdom 和 pnpm。浏览器只依赖 `DashboardQueryPort`，不直接访问 SQLite、TerminusDB、Redpanda、运行时会话文件或私有服务存储。通过环境变量配置读取 API 地址以及开发/预览监听地址和端口。未配置 API 时使用 fixture，并在界面明确标示演示数据；真实查询仅接受 `mode=live` 快照。

视觉与交互面向科研协作者、项目负责人和运维人员：清楚展示正式/候选边界、关注事项、阻塞原因、来源新鲜度、失败与结果未知；支持筛选和稳定 URL、手动刷新与可控轮询、窄屏布局、键盘焦点和非颜色状态表达。

## Acceptance Criteria

- [x] 完成独立 `package.json`、`pnpm-lock.yaml`、`src/` 和自动化测试。
- [x] 总览、路线、TaskNode 详情、知识与候选、运行观察页面均可运行。
- [x] 显示项目进度、TaskNode 前置关系和阻塞、正式 Wiki 与候选隔离、精确 ResourceVersion 资格、执行/MCP 失败事实、重复消息及监听服务状态。
- [x] 支持状态/文本筛选、稳定 URL 查询、手动刷新和可配置的自动刷新间隔。
- [x] 加载、空数据、部分来源失败、刷新失败、过期、未知状态及结果未知均有显式展示；旧快照在刷新失败时保留。
- [x] 页面只读，不提供创建、审核、发布、取消执行、重试或补发消息操作。
- [x] `corepack pnpm install --frozen-lockfile`、`corepack pnpm test`、`corepack pnpm run build` 通过。
- [x] 新增依赖的来源、用途、版本、许可证和验证命令已记入 README 与本工单。

## Notes

**2026-10-23T02:47:00+08:00**

完成前端交付。项目依赖来自 npm registry，固定范围见 `package.json`、完整解析见 `pnpm-lock.yaml`：Vue/Vite/Vitest/Pinia/Vue Router/Vue Test Utils/jsdom/`@types/node` 为 MIT，TypeScript 为 Apache-2.0。用途为界面运行、路由、状态管理、测试和构建；未增加 UI 组件库或运行时 API SDK。验证命令：`corepack pnpm install --frozen-lockfile`、`corepack pnpm test`（24 项通过）、`corepack pnpm run build`（通过）。

页面提供本地 fixture 演示和只读 `GET /api/dashboard/snapshot` 接入。真实来源的 Mapping、Wiki 只读适配器已由子工单完成；Gateway 与消息监听来源由 Frank Qi 负责的模块提供，接口尚未就绪。对应 Gitee issue：<https://gitee.com/qi-yueran/ai4science/issues/IKPT5I>。前端在这些来源不可用时明确展示 partial/unavailable，不将缺失来源伪装成空结果或成功状态。未修改 Frank Qi 负责的工单。

**2026-10-22T19:29:51Z**

﻿2026-10-23T03:20:00+08:00?????????????? `corepack pnpm test` ? 26 ????`corepack pnpm run build` ???Dashboard API `uv run --locked python -m unittest discover -s tests -v` ? 17 ????Research Mapping ? 77 ????5 ??? TerminusDB ???????LLM-Wiki ? 79 ????4 ??? TerminusDB ?????????????????????????????????????????Wiki ?????/????/?????????????????
