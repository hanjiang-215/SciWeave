# SciWeave

SciWeave 是面向多人科研协作的 Agent 驱动平台。它以正式研究路线组织任务及其依赖，让 Project Owner、研究人员和 Agent 围绕任务执行、证据提交、候选审核与正式发布开展协作，并保留可追溯的版本和治理记录。

本仓库是腾讯 AI4Sci 黑客松项目的工程仓库；SciWeave 是产品名称。核心领域术语和对象边界见[术语表](GLOSSARY.md)，技术选型及已裁决的部署形态见[技术栈说明](docs/TECH_STACK.md)和[架构决策记录](docs/adr/)。

## 产品目标与特点

- **以研究路线组织工作**：用 Research Mapping 表达研究任务、前置依赖、负责人及执行条件；路线视图是正式研究图的展示，不是另一份事实源。
- **由用户的 Agent 宿主承载交互**：通过 Harness 中的 Skills、MCP 卡片和本机配置使用平台能力，减少对专用管理界面的依赖。只读 Web 看板用于观察项目、任务、候选和服务状态。
- **把候选与正式事实分开**：Agent 不直接改写正式路线或正式知识。草稿、候选版本、预审报告、Owner 审核决定和正式版本各有边界。
- **执行结果可追溯**：Task Agent 的运行状态保存在本机执行记录中；研究结果作为草稿提交，并在审核后进入候选及正式发布流程。
- **按角色限制工具能力**：Project Owner、Researcher 和 Centre Agent 使用不同套件与身份令牌。某个 MCP 可访问，不代表调用者拥有该服务的全部能力。
- **集成端侧科研工具**：Task Agent 可调用 SciPal 等科研执行能力；平台负责任务路线、交接、治理和记录，科研工具的具体运行由端侧环境承担。

## 系统组成

```text
Project Owner 的 Harness
  ├─ Research Mapping / Wiki MCP：预览、审核、正式化
  ├─ Coordinator MCP：显式派发根任务
  └─ Registry / Email MCP：登记成员与通知
                         │
                         ▼
中央控制面（centre-stack）
  ├─ Research Mapping：正式研究路线与候选
  ├─ LLM-Wiki：正式知识文档与候选
  ├─ Draft Buffer：接收待审核草稿
  ├─ Centre Agent：候选预审与必要的合并候选
  ├─ Coordinator / Registry / Email Service
  ├─ Dashboard API + 只读 Web 看板
  └─ TerminusDB + Redpanda（独立基础服务）
                         ▲
                         │ MCP 与消息队列
                         │
Researcher 的 Harness + 本机 Task Agent
  ├─ 订阅任务交接并运行 Worker
  ├─ 通过 MCP 读取获授权的正式数据
  ├─ 将执行结果写入 Draft Buffer
  └─ 可连接 SciPal 与其他本地科研工具
```

中央业务服务目前由 `sci-weave/centre-stack/` 构建成一个镜像、一个容器，并由容器内的 supervisord 管理多个进程。TerminusDB 和 Redpanda 是独立服务，不包含在该业务镜像中。端侧套件安装在各自用户的 Harness 或本机 Task Agent 目录，不部署到中央容器。

| 组件 | 职责 |
|---|---|
| Research Mapping | 保存研究任务图及候选、正式版本之间的治理状态。 |
| LLM-Wiki | 保存正式知识文档、精确资源引用和知识候选。 |
| Draft Buffer | 接收尚未进入领域候选分支的 Mapping 或 Wiki 草稿，并执行配置的草稿审核规则。 |
| Centre Agent | 检查候选权限、版本基准和影响范围，写入预审结果；不替 Project Owner 批准或正式化。 |
| Coordinator | 在 Owner 明确请求后派发正式路线中的根任务；后续推进由交接事件和依赖关系驱动。 |
| Registry | 登记主体、工作流 Agent、运行实例及通知联系信息。 |
| Email Service | 接受通知意图并跟踪投递状态；真实邮件投递依赖部署环境中的 SMTP 配置。 |
| Dashboard API / Web UI | 聚合只读快照并显示项目、路线、候选、执行与监听服务状态。 |
| TerminusDB / Redpanda | 分别承担领域图存储和 Kafka 兼容消息队列职责；需要独立部署和配置。 |

## 角色与权限

| 角色 | 主要职责 | 权限边界 |
|---|---|---|
| **Project Owner（项目负责人）** | 维护项目路线；审查候选、预览影响并决定批准、退回或驳回；批准后正式化；登记主体和 Agent；显式派发根任务。 | 不绕过 Centre Agent 的候选预审，也不替 Researcher 执行其端侧工作。 |
| **TaskNode Owner（任务节点负责人）** | 按命名空间规则接纳或退回任务产生的草稿。 | 草稿接纳不等于 Mapping/Wiki 候选已获 Owner 正式批准。 |
| **Researcher（研究人员）** | 执行分配的科研任务，提交草稿或领域候选，并维护自己的 Task Agent。 | 可使用 Researcher 套件授权的能力，不负责 Owner 的正式审核和正式化。 |
| **Task Agent（任务 Agent）** | 在研究人员自己的机器上订阅交接、调用模型或科研工具并生成执行结果草稿。 | 不自行派发任务，不直接写入正式领域版本；能力由其获准的 MCP 卡片限制。 |
| **Centre Agent（中央 Agent）** | 对 Mapping 与 Wiki 候选进行预审，必要时形成合并候选，并记录判据版本和审计结果。 | 不审查原始草稿，不代替 Project Owner 批准或正式化，也不派发根任务。 |
| **Personal Agent（个人 Agent）** | 在 Codex、Cursor、WorkBuddy 等 Harness 中加载角色套件并协助用户操作。 | 不是独立的平台权限角色；实际权限来自套件配置和 MCP 身份令牌。 |

## 典型协作流程

1. **部署中央服务**：准备 TerminusDB、Redpanda 和 centre-stack；安全配置角色令牌、服务地址以及需要的 SMTP 或模型凭据。
2. **配置 Owner 套件**：Project Owner 在自己的 Harness 安装套件，配置 Mapping、Wiki、Coordinator、Registry 和 Email MCP 连接。
3. **建立项目与成员**：Owner 登记项目主体、Researcher、工作流 Agent 和运行实例，并指定任务负责人。
4. **制定研究路线**：Owner 提交 TaskNode 和依赖边变更。变更进入候选治理流程，正式 Mapping 只在审核并正式化后更新。
5. **派发根任务**：Owner 对正式路线中符合条件的根节点发起显式派发。其他节点根据正式依赖和上游交接推进，不通过任意命令绕过依赖。
6. **执行科研工作**：Researcher 或 Task Agent 接收任务并执行。Task Agent 的执行记录保存在端侧，其可用能力由对应 Agent 定义与 MCP 资源决定。
7. **提交草稿与证据**：执行结果通过 Draft Buffer 提交。配置的草稿审核人先完成草稿接纳；通过后再由领域 MCP 创建 Mapping 或 Wiki 候选。
8. **候选预审与 Owner 裁决**：Centre Agent 对候选预审并写入报告；Project Owner 查看候选差异、影响范围和预审结论后作出决定。
9. **正式发布并继续路线**：只有 Owner 批准且领域正式化完成后，内容才成为正式版本。Owner 可据此调整路线并显式启动新的根任务。

草稿接纳、候选预审和正式发布审核是不同阶段，不能把其中任一阶段的通过当作最终正式化。详细数据流和状态以 `docs/data-flow/`、`docs/TECH_STACK.md` 与领域服务接口为准。

## 快速开始

### 启动中央服务

在中央服务器先准备第三方基础服务及 `sci-weave/centre-stack/.env`。真实令牌、密码和模型密钥仅保存在部署机的 `.env`，不要提交到仓库。

```bash
cd sci-weave/centre-stack
cp .env.example .env
# 编辑 .env，填写必需令牌、公开 Origin 和第三方服务连接信息

docker compose --env-file .env up -d --build
docker compose --env-file .env run --rm bootstrap
docker compose --env-file .env ps
docker compose --env-file .env exec centre supervisorctl status
```

若使用仓库自带、以本地验证为目的的 Redpanda，需叠加 `compose.local-redpanda.yaml`：

```bash
docker compose --env-file .env \
  -f compose.yaml \
  -f compose.local-redpanda.yaml \
  up -d --build
```

该覆盖配置依赖名为 `redpanda_default` 的 Docker 网络。生产环境应将 Kafka bootstrap 和 broker 广播地址配置成业务容器实际可达的地址，不应使用指向容器自身的 `localhost`。

中央服务构建参数、端口、持久化、健康检查和运维说明见 [`sci-weave/centre-stack/README.md`](sci-weave/centre-stack/README.md)。

### 安装 Project Owner 套件

```bash
cd sci-weave/toolkits/project-owner-agent-toolkit
./install.sh
# 在 ~/.sciweave/owner/.env 中配置中央 MCP 地址与 Owner 令牌
./check.sh
```

### 安装 Researcher 套件

```bash
cd sci-weave/toolkits/researcher-agent-toolkit
./install.sh
# 在 ~/.sciweave/task-agent/.env 中配置中央 MCP 地址、Researcher 令牌和本机运行参数
./check.sh
```

安装后仍需按具体 Harness 的配置方式注册套件声明的 MCP 卡片和 Skills。变量名、地址和角色要求分别见 [Project Owner 套件说明](sci-weave/toolkits/project-owner-agent-toolkit/README.md) 与 [Researcher 套件说明](sci-weave/toolkits/researcher-agent-toolkit/README.md)。

## 安全与部署边界

- `.env`、真实令牌、SMTP 密码和模型 API Key 不提交；仓库只保存环境变量名称与占位示例。
- 中央 MCP 使用 Bearer 令牌。对公网提供服务时应通过经验证的 HTTPS 反向代理，并按最小权限原则限制直接暴露的端口。
- Web 看板和 Dashboard API 是只读观察面；CORS 不是认证机制。公网部署须由受信任的反向代理提供 HTTPS，并按需求增加访问控制。
- Research Mapping 与 LLM-Wiki 的领域对象、版本和治理边界彼此隔离；跨域关联通过稳定对象 ID 和版本 ID 表达。
- Task Agent 的执行记录不等同于正式科研结论；草稿、候选、预审结果和正式版本必须按各自状态解释。
- `sci-weave/service/` 中的服务用于独立验证或基础设施部署。仓库提供的单节点 Redpanda Compose 是本地验证配置，不是生产高可用部署方案。

## 项目布局

```text
sci-weave/
├── centre-control/      # 中央服务的独立子项目、项目组成员和 shared 代码
├── centre-stack/        # 中央业务服务的单容器部署单元
├── service/             # TerminusDB、Redpanda 等独立服务
└── toolkits/            # Project Owner、Researcher 等端侧套件

docs/
├── TECH_STACK.md        # 技术栈与部署边界
├── adr/                 # 架构决策记录
├── data-flow/           # 领域数据流说明
└── DEPENDENCIES.md      # 通用开发依赖与验证规则
```

## 当前实现范围

仓库包含中央服务部署单元、Mapping 与 Wiki 领域服务、草稿箱、Registry、Coordinator、Centre Agent Gateway、Project Owner 和 Researcher 套件，以及只读 Web 看板。各子项目是否在特定部署中完整可用，还取决于服务配置、令牌、Redpanda、TerminusDB、模型 API 和 SMTP 等外部条件；容器级健康状态不代表所有组件或业务来源均已就绪。

## 相关文档

- [领域术语表](GLOSSARY.md)
- [技术栈与部署边界](docs/TECH_STACK.md)
- [中央服务部署说明](sci-weave/centre-stack/README.md)
- [架构决策记录](docs/adr/)
- [Project Owner 套件](sci-weave/toolkits/project-owner-agent-toolkit/README.md)
- [Researcher 套件](sci-weave/toolkits/researcher-agent-toolkit/README.md)
