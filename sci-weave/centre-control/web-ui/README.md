# Web UI

SciWeave 中央服务器上的只读研究看板，用于查看 Research Mapping、LLM-Wiki、TaskNode、执行记录、消息事件和 Agent 监听服务状态。

产品领域规格见 [`docs/superpowers/specs/2026-10-22-web-dashboard-visibility-design.md`](../../../docs/superpowers/specs/2026-10-22-web-dashboard-visibility-design.md)。实现工单见 `ai4-san9`。

## 技术栈

- Vue 3.5
- Vite 7
- TypeScript 5
- Vue Router 4
- Pinia 3
- Vitest 3 + Vue Test Utils + jsdom
- pnpm 12

依赖来源均为 npm registry；Vue、Vue Router、Pinia、Vite、TypeScript、Vitest、Vue Test Utils、jsdom 和 `@types/node` 均采用 MIT 许可（jsdom 的运行时依赖遵循各自发布许可）。依赖只用于浏览器界面、路由、状态管理、测试和构建，不访问领域数据库或消息队列。版本约束、完整解析结果和完整许可证信息以 `package.json` 与 `pnpm-lock.yaml` 为准。

## 运行

在本目录执行：

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

不配置 API 地址时使用本地 fixture，可直接演示完整界面和异常状态。开发/预览监听地址和端口也可通过 `.env` 配置：

```dotenv
VITE_DEV_HOST=127.0.0.1
VITE_DEV_PORT=0
VITE_PREVIEW_HOST=127.0.0.1
VITE_PREVIEW_PORT=0
VITE_DASHBOARD_API_URL=<只读快照 API 的基地址>
```

实际部署地址、端口和认证代理由部署环境提供；不要把真实令牌写入前端环境变量或源码。浏览器请求的唯一业务接口是 `GET {VITE_DASHBOARD_API_URL}/api/dashboard/snapshot`，响应必须是统一的 `DashboardSnapshot`。

若前端与 API 不同源（不同主机、端口或协议），必须同时在后端配置 `SCIWEAVE_DASHBOARD_CORS_ORIGIN` 为本站的确切 origin，否则浏览器 CORS 预检会失败，界面持续提示"数据服务暂时无法连接"。推荐通过反向代理把前端与 `/api` 放在同一源下，这样无需 CORS。详见 [`../dashboard-api/README.md`](../dashboard-api/README.md) 的"跨源部署"一节。

## 验证

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm test:run
corepack pnpm run build
```

测试覆盖：

- 关注项排序、TaskNode 筛选和数据源新鲜度；
- 首次加载、空数据、部分数据、刷新失败保留旧快照、刷新并发和可控轮询；
- HTTP 只读请求、响应结构校验、非 2xx 和敏感错误信息脱敏；
- 状态徽章的可访问文本和动态更新；
- 总览、研究路线、任务详情、知识与候选、运行观察页面；
- 稳定 URL 筛选条件、消息重复、结果未知、精确 ResourceVersion 资格；
- 页面没有创建、编辑、审核、发布、取消、重试或补发消息的写入控件。

## 统一查询模型

`DashboardSnapshot` 的 `mode` 字段区分 `fixture` 与 `live`。未配置 `VITE_DASHBOARD_API_URL` 时界面会明确显示演示数据提示；配置后只接受聚合 API 返回的 `live` 快照。

- 来源状态：`fresh`、`stale`、`unavailable`、`partial`、`observedAt`；
- 项目、TaskNode 和前置节点关系；
- 正式 Wiki 文档、候选 Proposal、精确 `ResourceVersion` 及资格状态；
- ExecutionRecord、MCP 失败事实和结果未知；
- Task Agent/Centre Agent 监听服务状态、订阅范围和消费者组；
- 消息事件、业务幂等标识和重复投递标记。

HTTP 适配器只接受已校验的 JSON 快照，不会把服务端异常、令牌、堆栈或路径展示给浏览器。前端不读取 SQLite、TerminusDB、Redpanda、运行时会话文件或队列 offset 存储。

## 只读边界

看板不会执行领域写入、服务配置写入、消息补发、offset 提交、MCP 重试或自动恢复。任务下发、上游交接、领域 Agent 工作和人工处置仍由消息队列、领域 MCP 或 Gateway MCP 负责；看板只提供观察上下文和人工处理提示。
