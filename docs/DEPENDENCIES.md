# 项目依赖清单

更新日期：2026-10-16

## 结论

当前仓库已确定应用技术栈为 Node.js + pnpm，并在 `package.json` 中声明了首个运行时依赖 `@codemeall/harness-wiki`，锁文件 `pnpm-lock.yaml` 已提交。仓库目前仍没有应用源码入口、测试框架和 CI 配置，因此除该依赖外的运行时依赖尚未确定，不得在技术栈进一步确认前臆造。

## 已确认依赖

| 类别 | 依赖 | 用途 | 状态 |
| --- | --- | --- | --- |
| 运行时 | Node.js | 运行 pnpm 和后续应用代码 | 本机验证版本 v24.14.0 |
| 包管理 | pnpm | 声明依赖、生成并校验锁文件 | 已在 `package.json` 声明 `pnpm@12.11.2`；本机需通过 `corepack pnpm` 调用 |
| 版本控制 | Git | 分支、提交和协作 | 已配置 |
| 变更日志 | git-cliff | 根据 Conventional Commits 生成 `CHANGELOG.md` | 已配置 `cliff.toml` 并已生成 `CHANGELOG.md`；本机未安装 `git-cliff` |
| 任务跟踪 | fer | 管理需求、任务、状态和依赖关系 | 已初始化 `.tickets/`；本机未安装 `fer` |
| 创作平台 | SciencePal | 赛事作品的主要创作平台 | 文档中声明为外部平台；尚未接入代码或 API |
| 仓库协作 | gitee-cli（命令名：`gitee`） | 在 Gitee 远程仓库上执行仓库协作和 Pull Request 操作 | `0.7.1` 已在协作环境中验证；本机未安装 `gitee`，当前无法创建 PR |
| 运行时依赖 | `@codemeall/harness-wiki` | 维护 LLM Wiki / Harness Wiki 的 skill-first 工具 | 已在 `package.json` 声明 `^0.3.2`；按锁文件安装验证通过 |

### 技术栈与包管理记录（Node.js + pnpm）

- **来源**：提交 `1f920aa`（作者 Frank Qi <1206585163@qq.com>）引入 `package.json`、`pnpm-lock.yaml` 和 `.cursor/skills/ref/harness-wiki/SKILL.md`。
- **用途**：Node.js 是当前选定的应用运行时；pnpm 是当前选定的包管理器，依赖必须通过它在 `package.json` 中声明，并提交 `pnpm-lock.yaml`。
- **版本约束**：`package.json` 声明 `"packageManager": "pnpm@12.11.2"`，并通过 `devEngines.packageManager` 要求同名同版本、`onFail` 为 `download`。`pnpm@12.11.2` 在 registry 中存在（查询时最新为 `12.14.0`）；升级需重新验证安装和锁文件。Node.js 本机验证版本为 `v24.14.0`。
- **许可证或使用限制**：以 pnpm 发行包或上游仓库许可证为准。本机 npm/pnpm 使用的 registry 为 `registry.npmmirror.com`（依据安装与查询输出中的 tarball 地址）。
- **安装与验证**：
  - 本机直接执行 `pnpm --version` 失败，报错指向未安装的托管版本目录 `%LOCALAPPDATA%\pnpm\.tools\pnpm\12.11.2`；当前可用的调用方式是 `corepack pnpm <args>`。这是本机环境限制，不是锁文件或清单问题。
  - `corepack pnpm --version` 输出 `12.11.2`（corepack 自动下载该版本二进制）。
  - `corepack pnpm install --frozen-lockfile` 退出码 0：输出 `Lockfile is up to date` 和 `Lockfile passes supply-chain policies (93 entries)`，安装 93 个包并输出 `+ @codemeall/harness-wiki 0.3.2`；执行后 `git status` 无变化，`pnpm-lock.yaml` 未被修改。
  - `corepack pnpm test` 退出码 1：`test` 脚本目前是占位符 `echo "Error: no test specified" && exit 1`，仓库尚无真实测试。
  - 安装后 pnpm 提示 `Agent skills awaiting approval: @codemeall/harness-wiki`，本次未执行 `pnpm approve`。
  - `npm` 本机可用（`11.9.0`），但在仓库目录内执行会被 `devEngines` 拦截并报 `EBADDEVENGINES`，查询 registry 需在仓库目录之外执行。

### `@codemeall/harness-wiki` 依赖记录

- **来源**：由提交 `1f920aa` 引入，声明在 `package.json` 的 `dependencies` 中；包来自 npm registry（本机镜像为 `registry.npmmirror.com`）。仓库中的 `.cursor/skills/ref/harness-wiki/SKILL.md` 与依赖同名、由同一提交引入，提供该 wiki 的初始化和维护流程。
- **用途**：skill-first 的 LLM Wiki / Harness Wiki 脚手架与维护工具，用于初始化、写入、查询和检查 markdown 知识库。产品侧只参考它的 raw/source/entity/concept/synthesis 内容组织方式，不采用它的 MCP 或存储实现（见 `.tickets/ai4-saug.md`）。
- **版本约束**：`^0.3.2`；registry 中已发布版本为 `0.1.0`、`0.1.1`、`0.3.1`、`0.3.2`，锁文件解析到 `0.3.2`。升级需重新验证锁文件、安装结果和技能入口一致。
- **许可证**：MIT（依据 registry 元数据 `license = 'MIT'`）。
- **安装与验证**：`corepack pnpm install --frozen-lockfile` 安装成功并输出 `+ @codemeall/harness-wiki 0.3.2`；安装位置为 `node_modules/@codemeall/harness-wiki`。

### gitee-cli 依赖记录

- **来源**：项目协作规则 `.cursor/rules/dev/use_gitee.mdc`；当前使用 Gitee 仓库 `qi-yueran/ai4science`。
- **用途**：使用 `gitee pr create --base develop` 创建目标为 `develop` 的 Pull Request，并执行其他仓库协作操作。
- **版本约束**：已验证版本为 `gitee` 0.7.1；后续升级需重新验证 PR 创建和仓库操作命令。
- **许可证或使用限制**：以实际发行包或上游仓库许可证为准。不得提交访问令牌、密码或其他凭据。
- **Git 远程地址**：HTTPS 为 `https://gitee.com/qi-yueran/ai4science.git`，SSH 为 `git@gitee.com:qi-yueran/ai4science.git`；远程名称分别为 `origin` 和 `ssh_origin`。
- **凭据配置**：如需避免 HTTPS `push`/`pull` 反复输入账号密码，可执行 `git config --global credential.helper store`。该方式会将凭据明文保存到用户目录，仅适用于受信任的个人环境；共享环境应优先使用 SSH 或安全凭据管理器。
- **安装与验证**：协作环境曾通过 `gitee --version` 输出 `gitee 0.7.1`、`git config --get credential.helper` 输出 `store` 验证；当前本机未安装 `gitee`，因此 `gitee pr create` 无法执行。

## 本机环境现状

以下工具在下述环境中不可用，相关规范动作因此受阻，需在补齐环境后重新执行：

- `gitee`（gitee-cli）：未安装，无法创建目标为 `develop` 的 Pull Request。
- `fer`：未安装，无法创建工单或回写 issue tracker。
- `git-cliff`：未安装，无法执行 `git cliff --config cliff.toml --output CHANGELOG.md`。

## 当前缺失项

以下项目在后续阶段必须补齐：

1. 应用源码入口和最小可运行验证；目前仓库只有规则、文档和一个运行时依赖。
2. 真实测试：`test` 脚本仍是占位符，需补充测试框架和用例。
3. 构建和 CI 验证配置。
4. 运行所需环境变量名称、示例文件和安全说明；真实凭据不得提交。
5. 如需调用 SciencePal 或其他外部服务，应补充 API/服务依赖、访问方式、超时重试策略及降级方案。
6. fer 工单回写：本次依赖清单更新因本机未安装 `fer` 而未记录到 issue tracker。

## 补齐要求

- 先在 fer 任务中确认技术栈和验收标准，再添加具体依赖。
- 每个依赖必须说明用途、版本约束、来源和验证方式。
- 安装后必须生成并提交锁文件；缓存、构建产物、凭据和本地环境文件不得提交。
- 添加依赖后至少执行安装检查、测试或等价的最小可运行验证，并把结果回写 fer。
- 依赖变更使用 Conventional Commits 提交，并在提交前检查 `git diff` 和 `git diff --cached`。
