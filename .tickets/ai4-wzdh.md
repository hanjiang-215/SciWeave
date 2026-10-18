---
id: ai4-wzdh
status: closed
deps: []
links: []
created: 2026-10-16T14:32:58Z
type: task
priority: 2
assignee: SciWeave
parent: ai4-5vru
tags: [dependencies, setup, toolchain]
---
# 补齐本机缺失的三个开发工具（git-cliff / fer / gitee）

在 feature/zhanyunfei 的 Windows 开发机上补齐 docs/DEPENDENCIES.md「本机环境现状」中记录的三个缺失工具，使变更日志生成、工单管理和 Gitee PR 协作的规范动作可以实际执行。

## Acceptance Criteria

三个命令在本机可用且版本可追溯：git-cliff 2.14.2、fer 0.1.3、gitee 0.7.1；每个工具记录来源、版本、许可证、安装命令和验证输出；docs/DEPENDENCIES.md 与 humans/dev/DEPENDENCIES.md 同步更新；仓库中不提交任何凭据或本机绝对路径。

## Notes

**2026-10-16T14:35:23Z**

## 工具补齐完成

三个缺失工具已在本机安装并验证，规范动作的阻塞解除。

**git-cliff 2.14.2**：`npm install -g git-cliff@2.14.2` 安装。npm 包通过 optionalDependencies 提供 `git-cliff-windows-x64`，Windows 渠道可用。`git-cliff --version` 与 `git cliff --version` 均输出 `git-cliff 2.14.2`。在本仓库执行 `git-cliff --config cliff.toml --output <临时文件>` 退出码 0，并暴露出 `CHANGELOG.md` 落后提交历史 9 条条目（此前本机无 git-cliff 所致），已重新生成。

**Rust 1.99.1**：`winget install --id Rustlang.Rustup -e` 安装 rustup 1.29.1。首次安装后工具链处于中断状态（`missing manifest in toolchain`，重装报 `detected conflict: 'bin\rust-gdb'`），执行 `rustup toolchain uninstall stable` 清除残留后 `rustup toolchain install stable --profile minimal` 成功。链接器使用本机 Visual Studio 2017 Community 的 MSVC 14.16.27023。

**fer 0.1.3**：crate `ferricket`，`cargo install ferricket --locked` 安装。`fer --version` 输出 `fer 0.1.3`；`fer ls` 退出码 0，正确列出 13 个工单及阻塞关系。上游 GitHub Releases 为空，无预编译产物。

**gitee 0.7.1**：上游 `pkg-ai/gitee-cli` v0.7.1 无 Windows 产物（Release 仅 darwin-arm64 与 linux-musl；npm 包 optionalDependencies 仅 linux-x64 与 darwin-arm64，`@pkg-ai/gitee-cli-win32-x64` 在 registry 中返回 404），npm 路线在 Windows 不可用，改为源码构建。`cargo install --git` 直连超时，实际可用路径为 `git clone --depth 1 --branch v0.7.1 https://ghfast.top/https://github.com/pkg-ai/gitee-cli <目录>` 后 `cargo install --path <目录> --locked`。`gitee --version` 输出 `gitee 0.7.1`，`gitee pr create --help` 含 `--base`。

**文档**：`docs/DEPENDENCIES.md` 与 `humans/dev/DEPENDENCIES.md` 同步更新，新增 git-cliff、fer、Rust、gitee-cli 四份本机安装记录，并把「本机环境现状」改为已补齐状态；两份文件内容一致。

**遗留阻塞**：`gitee auth status` 输出 `Not authenticated`，创建目标为 `develop` 的 Pull Request 仍不可执行，需先完成 `gitee auth`；本机直连 `github.com` HTTPS 不稳定，涉及 GitHub 的下载需走镜像。

**2026-10-16T14:36:45Z**

## 提交与推送

分支 feature/zhanyunfei 已推送到 `origin`，推送范围 `a9b4593..131df11`，共 4 个提交：

- `fd4384e` docs(dependencies): record local install of git-cliff, fer and gitee
- `1ea43d3` docs(dependencies): sync human-facing copy with authoritative ledger
- `bfd5ae5` chore(fer): record toolchain installation
- `131df11` docs(changelog): record toolchain installation

**验证**：`git diff --check` 无空白错误；`git cliff --config cliff.toml --output CHANGELOG.md` 退出码 0，`CHANGELOG.md` 已补齐此前缺失的历史条目并纳入本次提交；`docs/DEPENDENCIES.md` 与 `humans/dev/DEPENDENCIES.md` 内容一致；工作区未提交凭据或本机绝对路径。

**遗留风险**：`gitee auth status` 仍为 `Not authenticated`，创建目标为 `develop` 的 Pull Request 不可执行，需要先在本机完成 `gitee auth` 才能验证 PR 流程；已记录在 `docs/DEPENDENCIES.md` 的「当前缺失项」第 7 条。

**后续观察**：`CHANGELOG.md` 中存在重复条目（例如 `docs(dependencies): Sync human-facing copy` 与 `chore(fer): Record Gitee pull request` 各出现两次），来自分支合并后的历史重复，属于 git-cliff 对合并分支不做去重的既有行为，不是本次引入。
