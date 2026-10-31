---
name: suite-release
description: 把两个 Agent 套件（PO 套件 / 研究员套件）从 develop 打成一个 Gitee 发行版。用户要求发版、发布套件、出 release、打 tag、发新版本给用户安装时使用；发版失败需要判断是拒绝点还是真故障时也使用。
---

# 套件发版

发版是低频、不可逆、有对外产物的操作：tag 一推、release 一建，用户就会按它下载安装。所以本技能的重点不是「跑哪个命令」，而是**在按下真发之前把该拒绝的情况拒绝掉**。

脚本在 `sci-weave/toolkits/release-scripts/`，操作说明在它的 `README.md`，设计依据在
[`docs/superpowers/specs/2026-10-31-suite-release-tooling-design.md`](../../../../docs/superpowers/specs/2026-10-31-suite-release-tooling-design.md)。

## 触发前先确认四件事

以下任一项不成立，**先停下问人**，不要用参数绕过去：

1. 版本号明确：目标是 `vX.Y.Z`，且两个套件 `suite.yaml` 的 `version:` 都已改成同一个 `X.Y.Z`；
2. 版本改动已合入 `develop`（发版以 `develop` 为基准，不从未合并的 feature 分支发）；
3. 工作区没有未提交改动（`release.sh` 会检查，但它只拒绝、不会替你整理）；
4. 有 Gitee 写权限：tag 推送靠 `origin`（HTTPS），release 与附件靠 `GITEE_TOKEN` 或 gitee-cli 配置。

用户只说「发个版」而没说版本号时，先读两个 `suite.yaml` 的当前版本，再问是沿用还是递增。

## 标准流程

```sh
cd sci-weave/toolkits/release-scripts

# 1. 看计划：同步 develop、打包、打 tag、建 release、传附件，全部只打印不执行
DRY_RUN=1 ./release.sh vX.Y.Z

# 2. 把计划讲给用户确认（版本、基准提交、三个附件名）

# 3. 真发
./release.sh vX.Y.Z
```

`release.sh` 依次做：前置检查 → 本地 `develop` 与 `origin/develop` 快进对齐（分叉则拒绝）→ `pack.sh` → `publish.sh`（`RELEASE_REF=develop PUSH_REMOTE=origin`）。

需要分步时用 `./pack.sh vX.Y.Z` 再 `./publish.sh vX.Y.Z`。**不要手工 `git tag`、`git push --tags` 或手工调 API 传附件**：手工打 tag 会让 tag 指到当前检出的 HEAD 而不是 `develop`，feature 分支内容就漏进发行版；tag 与 release 的 `target_commitish` 必须来自同一个 commit SHA。

## 拒绝点：修根因，不要绕

| 脚本怎么说 | 含义 | 正确动作 |
| --- | --- | --- |
| `suite versions disagree` | 两个套件版本不一致 | 把两个 `suite.yaml` 改成同一版本并合入 `develop` |
| `publish version ... does not match suite.yaml` | 传的 tag 与清单版本不符 | 对齐版本号；不要改脚本放宽校验 |
| `local develop and origin/develop have diverged` | 本地与远程分叉 | 人工解决分叉后再发；不要 `SKIP_SYNC=1` 假装没分叉 |
| `working tree has uncommitted changes` | 工作区脏 | 提交或 stash，并判断这些改动本该不该进本次发行版 |
| `existing tag ... points at ..., not ...` | 同名 tag 指向别的提交 | 判断是版本号复用还是历史 tag 错位，问人；不要强推 tag |
| `missing ... — run pack.sh ... first` | 没打包或版本对不上 | 先 `pack.sh` 同一版本 |
| `checksum mismatch`（用户侧） | 下载损坏或被动过 | 重新下载；仍失败则怀疑附件本身 |

`SKIP_SYNC=1`、`RELEASE_REF=master`、`PUSH_REMOTE=ssh_origin` 是**给明确意图准备的**（发未推送的 develop、出热修、换认证方式），不是失败时的逃生舱。用它们之前先向用户说明理由。

## 凭据与产物

- token 只从 `GITEE_TOKEN` 或 `~/.config/gitee/config.toml` 读；不要在命令里回显、不要写进文件、不要提交真实 `.env`。
- `dist/` 是构建产物，已被 `**/dist/` 忽略，不提交。
- 仓库是私有的，release 附件只对带 token 的请求可见；向用户交付下载链接时说明这一点。

## 发完要提供的证据

1. tag 与 release 链接：`https://gitee.com/<owner>/<repo>/releases/tag/vX.Y.Z`；
2. 附件清单：`sciweave-po-toolkit-X.Y.Z.zip`、`sciweave-researcher-toolkit-X.Y.Z.zip`、`SHA256SUMS`；
3. 用户侧安装验证命令：`./install-suite.sh researcher --version vX.Y.Z`（私有仓库需 `GITEE_TOKEN`）；
4. 把结果（版本、commit、release 链接、验证命令与输出）回写对应 fer 票。

## 边界

- 本技能只负责「从 develop 出一个发行版」。改代码、评审、合并进 `develop` 走 `implement`、`code-review`、`pr`。
- `centre-stack` 不走发行版附件，它是构建型组件（Dockerfile + compose），分发方式是部署包或镜像，别顺手把它塞进 zip。
- 套件装到哪、起什么服务，由套件自带的 `install.sh` 决定；`install-suite.sh` 只做下载、校验、解压、交接，不要在它里面重写安装逻辑。
