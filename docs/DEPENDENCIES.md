# 项目依赖清单

更新日期：2026-10-15

## 结论

当前仓库处于项目初始化阶段，只有规则、赛事文档和 Git 配置，没有源码、构建配置或包管理清单。因此，当前没有可以确认的运行时第三方依赖，也不能在未确定技术栈前臆造依赖。

## 已确认依赖

| 类别 | 依赖 | 用途 | 状态 |
| --- | --- | --- | --- |
| 版本控制 | Git | 分支、提交和协作 | 已配置 |
| 变更日志 | git-cliff | 根据 Conventional Commits 生成 `CHANGELOG.md` | 已配置 `cliff.toml`；尚未生成发布日志 |
| 任务跟踪 | fer | 管理需求、任务、状态和依赖关系 | 已初始化 `.tickets/`；当前任务为 `ai4-5vru` |
| 创作平台 | SciencePal | 赛事作品的主要创作平台 | 文档中声明为外部平台；尚未接入代码或 API |
| 仓库协作 | gitee-cli（命令名：`gitee`） | 在 Gitee 远程仓库上执行仓库协作和 Pull Request 操作 | 已安装 `gitee` 0.7.1；目标分支为 `develop` |

### gitee-cli 依赖记录

- **来源**：项目协作规则 `.cursor/rules/dev/use_gitee.mdc`；当前使用 Gitee 仓库 `OWNER/ai4science`。
- **用途**：使用 `gitee pr create --base develop` 创建目标为 `develop` 的 Pull Request，并执行其他仓库协作操作。
- **版本约束**：当前验证版本为 `gitee` 0.7.1；后续升级需重新验证 PR 创建和仓库操作命令。
- **许可证或使用限制**：以实际发行包或上游仓库许可证为准。不得提交访问令牌、密码或其他凭据。
- **Git 远程地址**：HTTPS 为 `https://gitee.com/OWNER/ai4science.git`，SSH 为 `git@gitee.com:OWNER/ai4science.git`；远程名称分别为 `origin` 和 `ssh_origin`。
- **凭据配置**：如需避免 HTTPS `push`/`pull` 反复输入账号密码，可执行 `git config --global credential.helper store`。该方式会将凭据明文保存到用户目录，仅适用于受信任的个人环境；共享环境应优先使用 SSH 或安全凭据管理器。
- **安装与验证**：当前环境 `gitee --version` 输出 `gitee 0.7.1`，`gitee pr create --help` 可查看 PR 创建参数，`git config --get credential.helper` 输出 `store`。

## 当前缺失项

以下项目在确定技术栈和产品边界后必须补齐：

1. 应用技术栈及对应包管理器，例如 Python/Node.js；目前不能据此选择依赖文件。
2. 运行时依赖声明和锁文件，例如 `pyproject.toml` 与锁文件，或 `package.json` 与锁文件。
3. 可重复的安装、开发、测试和构建命令。
4. 运行所需环境变量名称、示例文件和安全说明；真实凭据不得提交。
5. 最小源码入口、测试框架和 CI 验证配置。
6. 如果需要调用 SciencePal 或其他外部服务，应补充 API/服务依赖、访问方式、超时重试策略及降级方案。

## 补齐要求

- 先在 fer 任务中确认技术栈和验收标准，再添加具体依赖。
- 每个依赖必须说明用途、版本约束、来源和验证方式。
- 安装后必须生成并提交锁文件；缓存、构建产物、凭据和本地环境文件不得提交。
- 添加依赖后至少执行安装检查、测试或等价的最小可运行验证，并把结果回写 fer。
- 依赖变更使用 Conventional Commits 提交，并在提交前检查 `git diff` 和 `git diff --cached`。
