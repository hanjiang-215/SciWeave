# 套件发版工具与发版技能设计

- 日期：2026-10-31
- 状态：实现随本规格一并落地（脚本入库 + 发版技能）
- 范围：`sci-weave/toolkits/release-scripts/`、`.cursor/skills/engineering/suite-release/`、`.dsh/skills/engineering/suite-release/`
- 上游规格：[`2026-10-29-toolkit-project-deployment-and-harness-export-design.md`](2026-10-29-toolkit-project-deployment-and-harness-export-design.md)
- 上游票：[`ai4-5dq4`](../../../.tickets/ai4-5dq4.md)

## 1. 问题

两个 Agent 套件（`project-owner-agent-toolkit`、`researcher-agent-toolkit`）已经能打包、能安装，但发版这件事此前只存在于维护者本地的五个脚本里：

- 五个脚本从未入库，换机器或换人即丢失，也没法 review；
- 发版步骤只写在 `release-scripts/README.md` 里，Agent 要发版时得先被人告知「去看那个 README」，再自己回忆前置条件和失败处理；
- 版本一致性、基准分支、tag 指向这些隐性约束散落在脚本注释里，没有一处成文。

本规格把「脚本是什么」和「Agent 怎么发版」分开定清楚：脚本是可执行的实现，技能是给 Agent 的操作入口，规格是两者共同的依据。

## 2. 目标与非目标

### 2.1 目标

1. 五个脚本入库，按可执行位与只读文档的正常权限提交。
2. 新增发版技能 `suite-release`，让 Agent 能独立完成一次发版，并在失败时知道该拒绝而不是硬推。
3. 把脚本里隐含的不变量（版本一致、基准分支、幂等、凭据）写成成文契约。
4. 说明技能在 `.cursor/skills` 与 `.dsh/skills` 两处的存在方式与 Git 生命周期差异。

### 2.2 非目标

- 不改变套件自身的安装语义，`install.sh` 仍是安装行为的唯一来源；
- 不给 `centre-stack` 做发行版附件——它是构建型组件，分发方式是部署包或镜像，另议；
- 不引入新依赖：脚本只依赖 POSIX `sh`、`git`、`curl`、`zip`/`unzip`、`sha256sum`、`python3`；
- 不把发版做成 CI 流水线，仍由维护者本地触发。

## 3. 交付物一：五个脚本

目录固定为 `sci-weave/toolkits/release-scripts/`。它不是套件、不是子项目，没有部署单元，只是维护者工具，因此不放 `pyproject.toml`、不参与 `suitecheck`。

| 脚本 | 角色 | 契约 |
| --- | --- | --- |
| `pack.sh [ver]` | 打包含 | 输出 `sciweave-po-toolkit-<ver>.zip`、`sciweave-researcher-toolkit-<ver>.zip` 与 `SHA256SUMS` 到 `dist/`；剔除 `.venv`、缓存、`__pycache__`、`.env`；`dist/` 是构建产物，不入库 |
| `publish.sh [ver]` | 发release | 校验版本 → 从基准 ref 的**提交 SHA**打 tag 并推送 → 建 release → 上传三个附件；同 tag 已有 release 则复用，同名附件已存在则跳过 |
| `release.sh [ver]` | 一键入口 | 前置检查 → 本地 `develop` 与 `origin/develop` 快进对齐（分叉则拒绝）→ `pack.sh` → `publish.sh` |
| `install-suite.sh <po\|researcher>` | 用户侧 | 解析版本 → 下载 zip 与 `SHA256SUMS` → 校验 → 解压 → 调用套件自带 `install.sh`；校验失败拒绝安装 |
| `README.md` | 维护者与用户说明 | 版本来源、分支基准、token 前置条件、两条使用路径 |

### 3.1 不变量

- **版本来源单一**：版本号来自各套件 `suite.yaml` 的 `version:`。`publish.sh` 要求两个套件版本一致，且与传入 tag 一致，否则拒绝，避免发出一个由新脚本配旧包的版本。
- **基准分支**：默认 `develop`，tag 与 release 的 `target_commitish` 用同一个 commit SHA。tag 打在基准 ref 解析出的提交上，而不是当前检出的 HEAD，未合并的 feature 分支内容不会漏进发行版。热修用 `RELEASE_REF=master`。
- **幂等**：重复执行同一版本不产生重复 tag、重复 release 或重复附件。
- **凭据**：token 只从 `GITEE_TOKEN` 或 gitee-cli 配置读取，不写盘、不回显、不进日志。
- **无 `gitee release` 子命令**：`gitee-cli 0.7.x` 没有 `release`/`api` 子命令，因此发布走 Gitee OpenAPI + `curl`，这是刻意的降级路径，不是遗留物。

### 3.2 为什么不用 gitee-cli

`gitee help --json` 的 `unsupported_command_groups` 里列着 `api` 与 `release`，也没有逃生舱。因此 `publish.sh` 直接打 REST API；PR 与仓库协作仍走 `gitee` CLI，两者不冲突。

## 4. 交付物二：发版技能

### 4.1 两处位置与 Git 生命周期

技能落在两个路径，内容一致：

```text
.cursor/skills/engineering/suite-release/SKILL.md          # 事实源，入库
.cursor/skills/engineering/suite-release/agents/openai.yaml
.dsh/skills/engineering/suite-release/SKILL.md             # 派生副本，不入库
.dsh/skills/engineering/suite-release/agents/openai.yaml
```

两者的关系由根 `.gitignore` 第 37 行决定：`.dsh/` 整目录被忽略，注释写明「DSH 技能副本（由 `.cursor/skills` 派生，供 DSH 自动加载，可再生成）」。

因此：

- **`.cursor/skills/` 是唯一事实源**，任何技能内容修改都发生在这里，并随 PR 进入 `develop`；
- **`.dsh/skills/` 是派生副本**，供 DSH 自动加载，可随时由 `.cursor/skills/` 重新生成，**不进入 Git**；
- 本规格改变的不是这条派生关系，而是把「新增技能要同步两处」写成显式规则：新增或改动技能时，先写 `.cursor/skills/`，再同步到 `.dsh/skills/`，只提交前者。

派生副本不进 Git 是有意的：它是 Harness 的运行输入，不是产品交付物；把同一份技能内容提交两次会制造无意义的分叉与冲突。

### 4.2 技能职责

`suite-release` 是操作入口，不是脚本的复述。它必须让 Agent 做到：

1. **判断该不该发**：确认两个 `suite.yaml` 版本已改并合入 `develop`、工作区干净、本次要发的版本号明确；版本未变或分支未合入时先停下问人。
2. **先干跑再真发**：`DRY_RUN=1 ./release.sh vX.Y.Z`，把计划动作（同步、打包、tag、release、附件）讲清楚再做。
3. **只走 `release.sh` 或分步 `pack.sh` + `publish.sh`**：不手工 `git tag`、不手工 `git push --tags`、不手工调 API 传附件，避免 tag 与 release 指向错位。
4. **失败时拒绝而不是绕开**：版本不一致、本地 `develop` 与 `origin/develop` 分叉、tag 已存在且指向别的提交、校验和不匹配——这些都是设计好的拒绝点，只能修根因。
5. **不碰凭据与产物**：不把 token 写进命令历史以外的任何地方、不提交 `dist/`。
6. **发完给证据**：release 链接、附件名与 `SHA256SUMS`，以及用户侧安装的验证命令 `install-suite.sh <po|researcher> --version vX.Y.Z`。

技能的触发面是「发版/发布套件/release suite」这类意图，属于低频、不可逆、有对外产物的操作，因此技能默认要求人工确认后再执行真发。

### 4.3 与 `pr`、`implement` 技能的边界

`suite-release` 只管「从 `develop` 出一个发行版」这一刻。代码改动、评审、合并进 `develop` 仍走 `implement`、`code-review`、`pr`。发版产出的 tag 与 release 不回写代码，只回写 `ai4-5dq4` 及后续发版票的证据。

## 5. 验收

- [ ] 五个脚本入库，`sh -n` 语法检查通过，脚本保留可执行位、README 为 `644`。
- [ ] `pack.sh` 能在不联网的情况下产出两个 zip 与 `SHA256SUMS`。
- [ ] `DRY_RUN=1 ./release.sh vX.Y.Z` 打印完整计划且不改动仓库、不打 tag、不调写接口。
- [ ] 版本不一致时 `publish.sh` 拒绝并给出两个套件的实际版本。
- [ ] `suite-release` 技能在 `.cursor/skills/` 与 `.dsh/skills/` 两处可读，内容一致，只有前者入库。
- [ ] 本规格说明了两处技能位置与 `.dsh/` 不入库的理由。

## 6. 未做与后续

- 发版仍无 CI 校验（版本号递增、CHANGELOG 段落），当前由 `release.sh` 的前置检查与人工确认兜底。
- `centre-stack` 的分发方式未定，若后续出镜像或部署包，另立规格。
- 用户侧安装脚本的平台覆盖仍是 POSIX（`sh` + `unzip` + `sha256sum`），Windows 需走 WSL 或另做入口，见 `sci-weave/toolkits/WINDOWS.md`。
