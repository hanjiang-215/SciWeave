# 开发与 vibe coding 依赖

> 本文记录仓库协作、vibe coding 和本地验证所需的通用工具与依赖原则，不保存个人环境细节、绝对路径、临时日志或真实凭据。产品技术栈、子项目结构和运行时选择以 [TECH_STACK.md](TECH_STACK.md) 为准。

## 范围

本文只覆盖以下非产品依赖：

- 仓库协作与变更管理工具；
- agent 工作流和知识库工具；
- 本地验证服务及其容器运行前提；
- 根目录中已有的开发工具包。

Python 服务、MCP、Vue 前端及其业务依赖不在本文定义；它们必须由对应子项目的 `pyproject.toml`、`uv.lock`、`package.json` 和锁文件声明。同一项目组的多个 Python 子项目共享组级 `uv.lock`。

## 通用依赖清单

| 类别 | 依赖 | 用途 | 声明或配置位置 |
| --- | --- | --- | --- |
| 版本控制 | Git | 分支、提交、差异检查与远程协作 | Git 仓库与 `.cursor/rules/dev/use_git.mdc` |
| 仓库协作 | gitee-cli（`gitee`） | Gitee Pull Request 和仓库协作 | `.cursor/rules/dev/use_gitee.mdc` |
| 任务跟踪 | fer | 管理 `.tickets/` 中的 issue、状态和依赖 | `.cursor/rules/dev/use_fer.mdc` |
| 变更日志 | git-cliff | 按 Conventional Commits 生成 `CHANGELOG.md` | `cliff.toml` 与 `.cursor/rules/dev/use_gitcliff.mdc` |
| 根目录包管理 | Node.js + pnpm | 管理根目录 `package.json` 中的开发工具包 | `package.json` 与 `pnpm-lock.yaml` |
| 知识库工具 | `@codemeall/harness-wiki` | 维护 Harness Wiki 工作流 | 根目录 `package.json` 与 `.cursor/skills/ref/harness-wiki/` |
| 本地验证服务 | Docker Compose | 运行仓库提供的本地验证服务 | `sci-weave/centre-control/<服务名>/compose.yaml` |
| Research Mapping 验证 | TerminusDB | 验证 Schema、分支、版本和差异行为 | `sci-weave/centre-control/terminusdb/` |

## 使用原则

1. 每个工具、服务或包都必须有明确用途、来源、许可证或使用限制，以及可复现验证方式。
2. 新增开发依赖或本地验证服务前，先在 fer 中创建或更新对应任务；不要把技术决策只留在聊天记录中。
3. 依赖通过所属项目的清单和锁文件声明。根目录 Node 工具使用 `package.json` 与 `pnpm-lock.yaml`；独立 Python 子项目使用自身 `pyproject.toml` 与 `uv.lock`；同一项目组的 Python 子项目使用各自 `pyproject.toml` 和组级唯一 `uv.lock`；Vue 子项目使用自身的 `package.json` 与锁文件。
4. 开发工具的具体安装方式由使用者的操作系统和组织安全策略决定；不得将机器特定的安装步骤、代理、路径、版本输出或凭据写入本文件。
5. 真实令牌、密码、`.env`、缓存、日志、虚拟环境和构建产物不得提交。只提交环境变量名称和 `.env.example`。
6. 完成依赖变更后，运行相关的安装、测试或构建验证，并将命令和结果回写对应 fer 任务。

## 验证入口

- 根目录 Node 依赖：`corepack pnpm install --frozen-lockfile`。
- Python 子项目：独立子项目在其目录执行 `uv sync`；项目组在其根目录执行 `uv sync`，再执行对应子项目 README 中声明的测试命令。
- 本地服务：按对应 `sci-weave/centre-control/<服务名>/README.md` 启动和验证。
- 变更日志：按 `cliff.toml` 运行 `git cliff --config cliff.toml --output CHANGELOG.md`。
