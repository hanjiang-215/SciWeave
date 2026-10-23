# Web 看板实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `sci-weave/centre-control/web-ui` 交付一个可运行、可测试、只读的 Vue 看板，覆盖项目总览、TaskNode 路线、执行/服务状态和异常可见性。

**Architecture:** 前端通过 `DashboardQueryPort` 获取统一 `DashboardSnapshot`，fixture 与 HTTP 适配器实现同一接口。页面只消费展示模型，不直接访问 SQLite、TerminusDB、Redpanda 或私有服务存储。Vue Router 管理稳定 URL，Pinia 管理快照、筛选、刷新与轮询，组件按页面职责拆分。

**Tech Stack:** Vue 3、Vite、TypeScript、Vue Router、Pinia、Vitest、Vue Test Utils、jsdom、pnpm。

---

### Task 1: 建立独立前端项目与锁定依赖

**Files:**
- Create: `sci-weave/centre-control/web-ui/package.json`
- Create: `sci-weave/centre-control/web-ui/pnpm-lock.yaml`
- Create: `sci-weave/centre-control/web-ui/index.html`
- Create: `sci-weave/centre-control/web-ui/tsconfig.json`
- Create: `sci-weave/centre-control/web-ui/tsconfig.app.json`
- Create: `sci-weave/centre-control/web-ui/tsconfig.node.json`
- Create: `sci-weave/centre-control/web-ui/vite.config.ts`
- Create: `sci-weave/centre-control/web-ui/vitest.config.ts`
- Create: `sci-weave/centre-control/web-ui/.env.example`
- Modify: `sci-weave/centre-control/web-ui/README.md`

- [ ] **Step 1: 写入最小项目清单和工具配置**

`package.json` 声明 `dev`、`build`、`test`、`test:run` 和 `preview`，运行时只加入 Vue、Vue Router、Pinia；开发依赖加入 Vite、TypeScript、Vue 插件、Vitest、Vue Test Utils 和 jsdom。所有版本锁在子项目自身的 `pnpm-lock.yaml`，根目录依赖不变。

- [ ] **Step 2: 安装并生成锁文件**

Run: `corepack pnpm install`
Expected: 在 `sci-weave/centre-control/web-ui` 生成 `pnpm-lock.yaml`，依赖解析成功。

- [ ] **Step 3: 验证空项目构建**

Run: `corepack pnpm run build`
Expected: Vite 构建成功；之后再进入页面实现。

### Task 2: 用测试定义统一快照模型和派生状态

**Files:**
- Create: `sci-weave/centre-control/web-ui/src/domain/dashboard.ts`
- Create: `sci-weave/centre-control/web-ui/src/domain/dashboard.test.ts`
- Create: `sci-weave/centre-control/web-ui/src/data/fixtureSnapshot.ts`

- [ ] **Step 1: 写失败测试**

覆盖 `attentionItems` 按阻塞、失败、结果未知、过期排序；`filterTasks` 按状态和查询文本筛选；`sourceLabel` 区分 fresh、stale、unavailable、partial；`DashboardSnapshot` 保存来源、版本、观测时间和对象标识。

- [ ] **Step 2: 运行测试确认因模块不存在而失败**

Run: `corepack pnpm test:run -- src/domain/dashboard.test.ts`
Expected: FAIL，原因是领域模块尚不存在。

- [ ] **Step 3: 实现类型、fixture 和纯函数**

定义项目、TaskNode、执行记录、服务状态、消息事件、失败事实、数据源状态和快照类型；fixture 必须包含成功、阻塞、失败、结果未知、重复消息、过期服务和部分数据场景。

- [ ] **Step 4: 运行测试确认通过**

Run: `corepack pnpm test:run -- src/domain/dashboard.test.ts`
Expected: PASS。

### Task 3: 用测试实现查询端口和状态 Store

**Files:**
- Create: `sci-weave/centre-control/web-ui/src/data/queryPort.ts`
- Create: `sci-weave/centre-control/web-ui/src/data/fixtureQuery.ts`
- Create: `sci-weave/centre-control/web-ui/src/data/httpQuery.ts`
- Create: `sci-weave/centre-control/web-ui/src/stores/dashboard.ts`
- Create: `sci-weave/centre-control/web-ui/src/stores/dashboard.test.ts`

- [ ] **Step 1: 写失败测试**

测试 Store 初始加载、加载中、空结果、查询失败保留旧数据、部分数据标记、手动刷新和开启/关闭轮询；测试 HTTP 适配器只发 GET 请求并把非 2xx 响应转为安全错误。

- [ ] **Step 2: 运行测试确认失败**

Run: `corepack pnpm test:run -- src/stores/dashboard.test.ts`
Expected: FAIL，原因是查询端口和 Store 尚不存在。

- [ ] **Step 3: 实现查询端口和 Store**

`DashboardQueryPort` 只提供 `getSnapshot(signal?)`；fixture 适配器返回深拷贝，HTTP 适配器从 `VITE_DASHBOARD_API_URL` 请求只读快照。Store 负责快照、状态、错误、筛选、刷新和定时器清理；不暴露任何写入方法。

- [ ] **Step 4: 运行测试确认通过**

Run: `corepack pnpm test:run -- src/stores/dashboard.test.ts`
Expected: PASS。

### Task 4: 用组件测试实现通用状态和数据反馈

**Files:**
- Create: `sci-weave/centre-control/web-ui/src/components/StatusBadge.vue`
- Create: `sci-weave/centre-control/web-ui/src/components/SourceHealth.vue`
- Create: `sci-weave/centre-control/web-ui/src/components/EmptyState.vue`
- Create: `sci-weave/centre-control/web-ui/src/components/ErrorState.vue`
- Create: `sci-weave/centre-control/web-ui/src/components/StatusBadge.test.ts`

- [ ] **Step 1: 写失败组件测试**

验证状态徽章同时输出可见中文文本和可访问标签；来源状态显示更新时间；空数据、部分数据、失败和过期状态有不同文案。

- [ ] **Step 2: 运行测试确认失败**

Run: `corepack pnpm test:run -- src/components/StatusBadge.test.ts`
Expected: FAIL，原因是组件不存在。

- [ ] **Step 3: 实现组件**

使用语义 HTML、`aria-live` 和 CSS 状态变量；不能只用颜色表达状态，诊断信息可折叠但不丢失。

- [ ] **Step 4: 运行测试确认通过**

Run: `corepack pnpm test:run -- src/components/StatusBadge.test.ts`
Expected: PASS。

### Task 5: 实现总览、路线、执行与服务状态页面

**Files:**
- Create: `sci-weave/centre-control/web-ui/src/views/OverviewView.vue`
- Create: `sci-weave/centre-control/web-ui/src/views/RouteView.vue`
- Create: `sci-weave/centre-control/web-ui/src/views/OperationsView.vue`
- Create: `sci-weave/centre-control/web-ui/src/views/TaskDetailView.vue`
- Create: `sci-weave/centre-control/web-ui/src/views/views.test.ts`
- Create: `sci-weave/centre-control/web-ui/src/router.ts`
- Create: `sci-weave/centre-control/web-ui/src/App.vue`
- Create: `sci-weave/centre-control/web-ui/src/main.ts`

- [ ] **Step 1: 写页面行为测试**

验证首页显示项目进度、关注项和监听服务；路线页显示 TaskNode、前置关系和阻塞原因；运维页显示消息/MCP 失败、结果未知、重复事件和来源新鲜度；详情页能从稳定 URL 定位 TaskNode；DOM 中不存在创建、编辑、审核、发布、取消、重试等写入操作。

- [ ] **Step 2: 运行测试确认失败**

Run: `corepack pnpm test:run -- src/views/views.test.ts`
Expected: FAIL，原因是页面和路由尚不存在。

- [ ] **Step 3: 实现页面和路由**

采用深色实验室控制台视觉方向：暖白纸面内容区、墨黑导航、橙色关注状态和青色数据来源状态；保证响应式布局、键盘焦点、文字状态和稳定路由查询参数。页面只通过 Store 读取数据，不提供写入动作。

- [ ] **Step 4: 运行页面测试确认通过**

Run: `corepack pnpm test:run -- src/views/views.test.ts`
Expected: PASS。

### Task 6: 接入真实只读查询适配边界和运行配置

**Files:**
- Modify: `sci-weave/centre-control/web-ui/src/data/httpQuery.ts`
- Modify: `sci-weave/centre-control/web-ui/src/main.ts`
- Modify: `sci-weave/centre-control/web-ui/.env.example`
- Modify: `sci-weave/centre-control/web-ui/README.md`

- [ ] **Step 1: 增加 API 响应契约测试**

测试缺失来源、对象版本、`observed_at`、部分错误和不安全错误字段时的规范化行为；任何令牌、堆栈、服务器路径不进入 UI 错误。

- [ ] **Step 2: 实现环境变量选择和响应规范化**

有 `VITE_DASHBOARD_API_URL` 时使用 HTTP 查询，没有配置时使用 fixture 查询，开发和演示仍能启动。API 仅允许 GET 快照；写入请求没有客户端方法。

- [ ] **Step 3: 更新 README**

记录安装、开发、测试、构建、环境变量、fixture 模式、统一快照字段、真实查询接入要求和只读边界。

- [ ] **Step 4: 运行全量验证**

Run: `corepack pnpm install --frozen-lockfile && corepack pnpm test:run && corepack pnpm run build`
Expected: 全部通过。

### Task 7: 回写工单、检查变更并提交

**Files:**
- Modify: `.tickets/ai4-san9.md`
- Modify: `docs/tickets/meta/ai4-san9.toml`（如简介需要校正）

- [ ] **Step 1: 记录依赖和验证证据**

在 Notes 记录 Vue、Vite、TypeScript、Vue Router、Pinia、Vitest、Vue Test Utils、jsdom 的来源、用途、许可证/限制，以及冻结安装、测试和构建命令结果。

- [ ] **Step 2: 运行仓库级检查**

Run: `python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py check`、`git diff --check`。
Expected: 索引 OK，差异无空白错误。

- [ ] **Step 3: 提交可审查变更**

使用 Conventional Commit 提交源码、测试、锁文件、README 和工单证据；提交前确认没有 `.env`、缓存、构建产物或虚拟环境。
