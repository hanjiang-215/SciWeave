# 套件发行版工具

把两个 Agent 套件打成 Gitee 发行版，并提供一个用户侧的一键下载安装脚本。

三个套件里只有两个走这里：`project-owner-agent-toolkit`（PO 套件）和
`researcher-agent-toolkit`（研究员套件）。**中央服务（centre-stack）不走发行版附件**——
它是构建型组件（Dockerfile + compose），正确的分发方式是部署包或镜像，另议。

## 为什么不用 gitee-cli

`gitee-cli 0.7.x` 没有 `release` 子命令（`gitee help --json` 的
`unsupported_command_groups` 里列着 `api`、`release` 等），也没有 `gitee api` 逃生舱。
所以发布走 Gitee OpenAPI + `curl`，`publish.sh` 就是这层封装。

## 三个脚本

| 脚本 | 谁用 | 干什么 |
|---|---|---|
| `pack.sh [ver]` | 维护者 | 打两个 zip 到 `dist/`，剔 `.venv`/缓存/`.env`，生成 `SHA256SUMS` |
| `publish.sh [ver]` | 维护者 | 从 `develop` 打 tag → 建 release → 上传两个 zip + SHA256SUMS |
| `release.sh [ver]` | 维护者 | 一键：同步本地 develop → 打包 → 发布（推荐入口） |
| `install-suite.sh <po\|researcher>` | 最终用户 | 从 release 下载、校验、解压、调用套件自带的 `install.sh` |

版本号来自各套件 `suite.yaml` 的 `version:`；发布时 `publish.sh` 会校验两个套件版本一致、
且与传入的 tag 一致，否则拒绝。

**发行版基准分支：`develop`，以本地 develop 的进度为准。** `release.sh` 先把本地
`develop` 与 `origin/develop` 快进对齐（只做 fast-forward，分叉时拒绝继续），再把 tag
打到本地 develop 的 commit 上。tag 与 release 的 `target_commitish` 用同一个 commit SHA，
防止两者错位。`SKIP_SYNC=1` 可跳过同步（当你要发一个尚未推送的本地 develop）。
需要从别的 ref 出热修版时用 `RELEASE_REF=master ./publish.sh vX.Y.Z`。

tag 推送默认走 `origin`（HTTPS）。`ssh_origin` 可能以另一个无仓库写权限的账号认证，
所以不优先使用；需要时用 `PUSH_REMOTE=ssh_origin` 覆盖。

## 维护者：发一个版本（推荐 `release.sh`）

```sh
cd sci-weave/toolkits/release-scripts

# 1. 改两个 suite.yaml 的 version，例如 0.1.0 -> 0.2.0，提交并合入 develop
# 2. 干跑，看清楚会做什么，不实际改动
DRY_RUN=1 ./release.sh v0.2.0
# 3. 真发布（同步本地 develop → 打包 → 打 tag → 建 release → 传附件）
./release.sh v0.2.0
```

也可以分步手动做：`./pack.sh v0.2.0` 后 `./publish.sh v0.2.0`（步骤见下）。

`publish.sh`/`release.sh` 幂等：同 tag 已有 release 就复用、已有同名附件就跳过、远端已存在
且同 commit 的 tag 就跳过 push，重跑安全。token 只从环境变量或 `~/.config/gitee/config.toml`
读取，不落盘、不回显。

> 仓库是私有的，release 附件也只对带 token 的请求可见。用户侧下载需要设置
> `GITEE_TOKEN`（或把仓库/发行版改为公开）。

## 用户：装一个套件

```sh
# 最新版
./install-suite.sh po
./install-suite.sh researcher

# 指定版本
./install-suite.sh researcher --version v0.1.0

# 私有仓库需要 token
GITEE_TOKEN=xxxx ./install-suite.sh po
```

`install-suite.sh` 只做「下载 + 校验 + 解压 + 交接」；装到哪、起什么服务，仍由套件自带的
`install.sh` 决定（见各套件 README）。校验失败会直接拒绝安装。

## 产物与 .gitignore

`dist/` 是构建产物，已被根 `.gitignore` 的 `**/dist/` 忽略，不入库。
