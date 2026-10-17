# 项目依赖清单

更新日期：2026-10-16

## 结论

当前仓库已确定应用技术栈为 Node.js + pnpm，并在 `package.json` 中声明了首个运行时依赖 `@codemeall/harness-wiki`，锁文件 `pnpm-lock.yaml` 已提交。仓库目前仍没有应用源码入口、测试框架和 CI 配置，因此除该依赖外的运行时依赖尚未确定，不得在技术栈进一步确认前臆造。

开发工具链方面，原先缺失的三个命令已在本机补齐：`git-cliff` 2.14.2、`fer` 0.1.3 和 `gitee` 0.7.1，变更日志生成、工单管理和 Gitee 协作的规范动作已可实际执行。`gitee` 尚未登录，因此创建 Pull Request 仍不可用。

## 已确认依赖

| 类别 | 依赖 | 用途 | 状态 |
| --- | --- | --- | --- |
| 运行时 | Node.js | 运行 pnpm 和后续应用代码 | 本机验证版本 v24.14.0 |
| 包管理 | pnpm | 声明依赖、生成并校验锁文件 | 已在 `package.json` 声明 `pnpm@12.11.2`；本机需通过 `corepack pnpm` 调用 |
| 版本控制 | Git | 分支、提交和协作 | 已配置 |
| 变更日志 | git-cliff | 根据 Conventional Commits 生成 `CHANGELOG.md` | 已配置 `cliff.toml` 并已生成 `CHANGELOG.md`；本机已安装 `git-cliff` 2.14.2 |
| 任务跟踪 | fer | 管理需求、任务、状态和依赖关系 | 已初始化 `.tickets/`；本机已安装 `fer` 0.1.3，可读写全部工单 |
| 构建工具链 | Rust（rustup / cargo） | 从源码编译 `fer` 和 `gitee`，二者当前无 Windows 预编译产物 | 本机已安装 rustup 1.29.1、rustc/cargo 1.99.1（`stable-x86_64-pc-windows-msvc`） |
| 创作平台 | SciencePal | 赛事作品的主要创作平台 | 文档中声明为外部平台；尚未接入代码或 API |
| 仓库协作 | gitee-cli（命令名：`gitee`） | 在 Gitee 远程仓库上执行仓库协作和 Pull Request 操作 | 本机已安装 `gitee` 0.7.1（源码构建）；尚未登录，创建 PR 仍需先认证 |
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
- **安装与验证**：协作环境曾通过 `gitee --version` 输出 `gitee 0.7.1`、`git config --get credential.helper` 输出 `store` 验证。本机改用源码构建，见下节「gitee-cli 本机安装记录」。

### git-cliff 工具记录

- **来源**：上游仓库 `https://github.com/orhun/git-cliff`；npm 官方发行包 `git-cliff`（本机镜像为 `registry.npmmirror.com`）。
- **用途**：按 `cliff.toml` 的 Conventional Commits 分组规则生成或更新根目录的 `CHANGELOG.md`。
- **版本约束**：本机安装 `2.14.2`（查询时 `latest` 为 `2.14.2`）。npm 包通过 `optionalDependencies` 分发各平台二进制，Windows 对应 `git-cliff-windows-x64` 和 `git-cliff-windows-arm64`，因此该渠道在 Windows 上可用。
- **许可证**：MIT OR Apache-2.0（依据 registry 元数据）。
- **安装与验证**：
  - 安装命令：`npm install -g git-cliff@2.14.2`（输出 `added 25 packages`）。
  - `git-cliff --version` 输出 `git-cliff 2.14.2`。
  - `git cliff --version` 同样输出 `git-cliff 2.14.2`，说明规则中使用的 `git cliff` 子命令形式可用。
  - 在本仓库执行 `git-cliff --config cliff.toml --output <临时文件>` 退出码 0，仅在临时文件生成结果，未改动 `CHANGELOG.md`。
  - 该次试运行暴露出 `CHANGELOG.md` 已落后于提交历史：生成结果比仓库中已提交的版本多出 9 条条目（`fix(rules)`、`docs(rules)`、`docs(changelog)`、`docs(dependencies)` 等），原因是此前本机没有 `git-cliff`。本次已重新生成并提交。

### fer 工具记录

- **来源**：crates.io 上的 crate `ferricket`（仓库 `https://github.com/prabirshrestha/ferricket`），安装后的可执行文件名为 `fer`。
- **用途**：本仓库唯一的 issue tracker，管理 `.tickets/` 下的工单、状态、依赖关系、关联和评论。
- **版本约束**：本机安装 `0.1.3`（当前最新版本）。上游不提供任何预编译产物，GitHub Releases 为空，因此只能用源码编译。
- **许可证**：MIT（依据 crates.io 版本元数据）。
- **安装与验证**：
  - 安装命令：`cargo install ferricket --locked`，输出 `Installed package ferricket v0.1.3 (executable fer.exe)`。
  - `fer --version` 输出 `fer 0.1.3`。
  - `fer --help` 暴露 `create`、`start`、`close`、`status`、`dep`、`link`、`ls`、`ready`、`blocked`、`show`、`add-note`、`query` 等子命令，与 `.cursor/rules/dev/use_fer.mdc` 描述的工作流一致。
  - 在本仓库执行 `fer ls` 退出码 0，正确列出 13 个工单及其状态和阻塞关系。
  - `fer create`、`fer start`、`fer add-note` 已实际用于创建并推进工单 `ai4-wzdh`。

### Rust 工具链记录

- **来源**：`rustup` 由 winget 包 `Rustlang.Rustup` 安装，工具链来自 `static.rust-lang.org`，crate 依赖来自 crates.io。
- **用途**：`fer`（ferricket）和 `gitee`（gitee-cli）都没有 Windows 预编译产物，必须在本机编译。
- **版本约束**：rustup 1.29.1；默认工具链 `stable-x86_64-pc-windows-msvc`，即 rustc 1.99.1、cargo 1.99.1。
- **许可证**：Rust 工具链按 MIT / Apache-2.0 双许可发布。
- **安装与验证**：
  - 安装命令：`winget install --id Rustlang.Rustup -e --accept-source-agreements --accept-package-agreements`。
  - 首次执行 winget 安装后工具链处于中断状态，`rustup show` 报 `error: missing manifest in toolchain`，`rustup toolchain install stable` 报 `detected conflict: 'bin\rust-gdb'`。处理方式为先 `rustup toolchain uninstall stable` 清除残留目录，再重新安装。
  - `rustup toolchain install stable --profile minimal` 输出 `stable-x86_64-pc-windows-msvc installed - rustc 1.99.1 (58cf8f9c3 2026-10-13)`。
  - `cargo --version` 输出 `cargo 1.99.1 (5f94df478 2026-08-27)`；`cargo install` 使用本机 Visual Studio 2017 Community 自带的 MSVC 14.16.27023 链接器。
  - 安装目录 `%USERPROFILE%\.cargo\bin` 已在用户 PATH 中，新开的终端可直接调用 `cargo`、`fer`、`gitee`。

### gitee-cli 本机安装记录

- **上游**：`https://github.com/pkg-ai/gitee-cli`，tag `v0.7.1`；crate 名 `gitee-cli`，`[[bin]] name = "gitee"`。
- **许可证**：MIT（依据仓库 `Cargo.toml` 和 npm 包元数据）。
- **Windows 无预编译产物**：
  - GitHub Release `v0.7.1` 的产物只有 `gitee-v0.7.1-aarch64-apple-darwin.tar.gz`、`gitee-v0.7.1-x86_64-unknown-linux-musl.tar.gz` 和校验和文件，没有 Windows 目标。
  - npm 包 `@pkg-ai/gitee-cli@0.7.1` 的 `optionalDependencies` 只有 `@pkg-ai/gitee-cli-linux-x64` 和 `@pkg-ai/gitee-cli-darwin-arm64`；`@pkg-ai/gitee-cli-win32-x64` 等其他平台包在 registry 中不存在（404）。因此 `npm install -g @pkg-ai/gitee-cli` 在本机只能装到 JS 包装层，拿不到可执行文件。
- **安装与验证**：
  - 因上游无 Windows 产物，改为源码构建。`cargo install --git https://github.com/pkg-ai/gitee-cli --tag v0.7.1` 在本机反复超时失败（`failed to receive response: 操作超时`），`git clone` 直连 `github.com` 也曾报 `Failed to connect to github.com port 443`。
  - 实际可用路径：先用 git 通过镜像克隆，再本地安装。本机可用的镜像为 `https://ghfast.top/`（`gh-proxy.com`、`ghproxy.net` 同样可用）：
    - `git clone --depth 1 --branch v0.7.1 https://ghfast.top/https://github.com/pkg-ai/gitee-cli <目录>`
    - `cargo install --path <目录> --locked`
  - 构建输出 `Installed package gitee-cli v0.7.1 (executable gitee.exe)`。
  - `gitee --version` 输出 `gitee 0.7.1`；`gitee pr create --help` 输出包含 `--repo`、`--head`、`--base`、`--title` 等参数，与规则中的 `gitee pr create --base develop` 一致。
  - `gitee auth status` 输出 `Not authenticated`，说明本机尚未登录，创建 Pull Request 之前仍需先完成认证；认证凭据不得提交到仓库。
  - 直连 `github.com` 的可用性在本机不稳定（本仓库自身的 Gitee 远程不受影响），后续按需改用镜像或 `ssh_origin`。

## 本机环境现状

原先缺失的三个工具已在本机补齐，规范动作的阻塞已解除：

| 命令 | 版本 | 安装渠道 | 状态 |
| --- | --- | --- | --- |
| `git-cliff`（同时支持 `git cliff`） | 2.14.2 | npm 全局安装 | `git-cliff --version`、`git cliff --version` 均通过 |
| `fer` | 0.1.3 | `cargo install ferricket` | `fer --version`、`fer ls` 通过，已读写工单 |
| `gitee` | 0.7.1 | Rust 源码构建（上游无 Windows 产物） | `gitee --version`、`gitee pr create --help` 通过；`gitee auth status` 为 `Not authenticated` |

遗留阻塞：`gitee` 未登录，因此创建目标为 `develop` 的 Pull Request 仍不可执行，需要先完成 `gitee auth` 认证；本机直连 `github.com` HTTPS 不稳定，涉及 GitHub 的下载需要走镜像。

## 当前缺失项

以下项目在后续阶段必须补齐：

1. 应用源码入口和最小可运行验证；目前仓库只有规则、文档和一个运行时依赖。
2. 真实测试：`test` 脚本仍是占位符，需补充测试框架和用例。
3. 构建和 CI 验证配置。
4. 运行所需环境变量名称、示例文件和安全说明；真实凭据不得提交。
5. 如需调用 SciencePal 或其他外部服务，应补充 API/服务依赖、访问方式、超时重试策略及降级方案。
6. fer 工单回写：本机已安装 `fer`，工具补齐过程已记录到工单 `ai4-wzdh`（`.tickets/ai4-wzdh.md`）。
7. `gitee` 认证：`gitee` 已安装但未登录，创建 Pull Request 前需要完成 `gitee auth`；访问令牌等凭据只在本机保存，不得写入仓库。

## 补齐要求

- 先在 fer 任务中确认技术栈和验收标准，再添加具体依赖。
- 每个依赖必须说明用途、版本约束、来源和验证方式。
- 安装后必须生成并提交锁文件；缓存、构建产物、凭据和本地环境文件不得提交。
- 添加依赖后至少执行安装检查、测试或等价的最小可运行验证，并把结果回写 fer。
- 依赖变更使用 Conventional Commits 提交，并在提交前检查 `git diff` 和 `git diff --cached`。
