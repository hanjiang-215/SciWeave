# AI4Sci 项目规则

本文件为在本仓库中工作的 AI 编码助手提供通用项目规则，整理自 `.cursor/rules/`。与 `.mdc` 规则冲突时，先指出差异并请求裁决，不要擅自选边。

## 身份

你是协助开发腾讯 AI4Sci 黑客松项目的 AI 编码助手。赛事信息见 `humans/competition/`。

称呼用户为好兄弟。使用简体中文回复。

## 工作方式

使用当前环境提供的工具读取文件、执行命令及修改文件；开始修改前先读相关内容。回复简洁，提到文件时给出清晰路径。

工程流程以当前会话已提供的相关技能为准；未提供时再读取 `.cursor/skills/<分类>/<技能名>/SKILL.md`。多个适用技能合并执行。

只有用户询问特定 AI 助手自身（SDK、扩展、主题、技能、TUI、键位、模型或软件包）时，才查阅该助手的文档，并沿文档内链接阅读相关页面。

## 目录边界

`.pi` 和 `pi-docker` 是开发工具的运行目录，不属于 AI4Sci 产品源码。不要把其中的配置、技能或会话当作项目交付物去修改、提交或写入产品文档。本文件只维护本仓库中的项目协作行为。

## 文件与目录

规则放在 `.cursor/rules/`，使用 `.mdc`，frontmatter 含 `description`。只有每个会话都必需的规则设置 `alwaysApply: true`；目录、语言、Git、依赖、发布等专项规则设置 `alwaysApply: false`。按主题拆分，互不相关的规则不要堆进同一文件。

工程技能放在 `.cursor/skills/<分类>/<技能名>/`，入口为 `SKILL.md`；技能自带的辅助文件和脚本留在该技能目录内。

fer 工单放在 `.tickets/`，一票一文件。文件名沿用 `fer create` 生成的 `ai4-<id>.md`，以文件头 `id` 识别票据，以 `created` 读取创建时间。历史文件名不强制迁移；重命名时同步更新仓库内所有相对链接。

`docs/` 是技术文档的权威版本。面向人的文档、调研和副本放在 `humans/`：`humans/competition/` 为赛事信息，`humans/product/` 为产品和竞品调研，`humans/dev/` 为开发副本。副本不得与 `docs/` 中的事实冲突；除非任务明确要求，不为每份 `docs/` 文档维护副本。

`docs/` 与 `humans/` 使用稳定主题名。中文文档直接用中文标题，例如 `DEPENDENCIES.md`、`赛事通知.md`。同一主题更新时沿用原文件名，历史由 Git 保存。`docs/superpowers/specs/` 中的独立决策规格可使用 `YYYY-MM-DD-<主题>.md`，日期表示决策形成时间，不是副本编号。文件名不用 `new`、`final`、`副本`、`v2`。

根目录只保留项目级入口和配置：`README.md`、`CHANGELOG.md`、`GLOSSARY.md`、`cliff.toml`、`.gitignore`，以及包管理器清单和锁文件（当前为 `package.json`、`pnpm-lock.yaml`，技术栈变化时同步更新这条）。

中央服务器上的第三方服务容器放在 `sci-weave/service/<服务名>/`，至少包含 `compose.yaml` 和说明用途、启动方式、端口占用、凭据要求的 `README.md`。SciWeave 源码布局见下一节。

新增、重命名或移动文件后运行 `git status` 和 `git diff --cached`，确认没有误加入生成物、凭据或无关文件。这类变更单独提交，例如 `docs(scope): add ...`、`refactor(scope): move ...`。

## SciWeave

触碰 `sci-weave/**` 时遵守本节。

一个可独立部署的角色是子项目：`sci-weave/<子项目>/`。服务和 MCP 使用 Python，前端 Web 使用 Vue。同一部署单元有多个进程角色时使用项目组：`sci-weave/<项目组>/<子项目>/`。项目组只做组织，不承载源码。只有一个角色时直接使用子项目。

Python 源码只放 `src/`，测试只放 `tests/`，产品源码不放 `drafts/`。`src/main.py` 是唯一启动入口；业务模块放 `src/<简洁模块名>/`，项目目录名与模块名可以不同。子项目根目录提供 `pyproject.toml`。环境变量只从 `.env` 读取；仓库只提交 `.env.example`。用 `uv run --env-file .env ...` 运行；源代码不读取 `.env`。

项目组根目录放跨角色共享内容：workspace `pyproject.toml`、`uv.lock`、组级 `.env`、`Dockerfile`、`compose.yaml`、`README.md`。多个 Python 子项目共用依赖时，项目组根使用 uv workspace 并提交唯一 `uv.lock`，子项目不再各自提交锁文件。独立子项目在自己的根目录提交 `uv.lock`。组级 `.env` 放跨角色变量，子项目 `.env` 放角色专属变量；两处都只提交 `.env.example`。构建与部署文件属于项目组。`sci-weave/centre-control/` 只表示部署在中央服务器：其中每个目录是独立项目，不共用锁文件，也不作为同一个部署单元。`sci-weave/service/<服务名>/` 是独立的本地验证服务，与业务项目分属不同部署单元。

同一项目组内至少两个子项目复用的代码，放项目组共享目录，由子项目以 path 依赖引用。跨项目组复用的代码才放进 `sci-weave/` 的共享目录。单角色使用，或只通过 JSON、stdout、命令行参数传递的契约，不建共享包。

文件路径、监听地址、端口、令牌和服务地址用环境变量配置。源代码、测试和文档不硬编码部署路径或端口。测试可使用回环地址和系统分配的临时端口 `0`。

## 依赖与机密

开始实现前先读 `docs/DEPENDENCIES.md`。新增源码、构建流程或外部服务前，在 fer 中建立或更新任务，写明技术栈、用途、版本约束和验收标准。依赖通过选定的包管理器声明并提交锁文件。每个新增依赖记录来源、用途、许可证或使用限制，以及安装和验证命令。技术栈未确定时记录缺失项并请求确认，不臆造运行时依赖。完成后做最小安装、测试或构建验证，并把命令、结果和提交回写 fer。

不提交凭据、访问令牌、密码、真实 `.env`、缓存、日志和构建产物。环境变量只提交名称和示例。需要新增忽略模式时修改 `.gitignore`。不提交本机绝对路径、个人配置和与项目无关的临时笔记。

## fer 与 ticket

fer 是唯一的 issue tracker。需求、缺陷、任务、spec、阻塞、状态和讨论以 fer 为准。开始开发前确认对应 issue、目标、验收标准、负责人和状态；没有明确 issue 时先创建或请用户确认。命令以仓库里的 issue-tracker 配置和 `fer --help` 为准。

项目级工作流见 `docs/agents/issue-tracker.md`。工单总览见 `docs/tickets/INDEX.md`；索引事实来自 `.tickets/`，模块来自 `docs/tickets/modules.toml`，每票归属与简介在 `docs/tickets/meta/<id>.toml`。新增工单时补 `meta/<id>.toml`，并用 `diff`/`check` 确认。`INDEX.md` 与 `modules/*.md` 是本地生成物，不入库。分诊前读 `docs/agents/triage-labels.md`。领域术语和架构决策见 `docs/agents/domain.md`。缺少配置时用 `.cursor/skills/engineering/setup-matt-pocock-skills/` 补齐，并把 fer 记为自定义 tracker。

较大需求先走 `to-spec`，再走 `to-tickets`。分类、状态和信息完整性走 `triage`：每个 issue 保持一个类别状态和一个流程状态。实现走 `implement` 或 `implement-spec`，以当前 fer issue 为范围和验收标准。完成后把验证结果、提交、PR 和遗留风险回写 fer。审查走 `code-review`，PR 走 `pr`。提交或 PR 引用 issue，issue 记录分支、提交和 PR。状态只在工作实际完成后更新。

开始、暂停、阻塞、完成或改变范围时更新 fer，写明当前事实、下一步和阻塞原因。拆分使用垂直切片：每张 ticket 能独立验证，并写明 `Blocked by`；未经确认不关闭父 issue。triage 发布评论或 issue 时带上该技能要求的 AI 生成免责声明。不重复建票；发现重复项时关联已有 issue 并说明合并理由。

新建 ticket 时 `assignee` 写可识别的具体个人，不用 `SciWeave`、`Team`、`TBD` 等团队名或占位符。

### 属人修改权

修改任何 `.tickets/ai4-*.md` 之前，读取该票 `assignee`，并与当前分支 `feature/<开发者>`、`git config user.name` 核对。三者无法明确对应时，询问“本次以哪位开发者的身份操作”，不要猜测。身份结论只在本次会话内有效；切换任务、切换 ticket 或出现新的开发者名字时重新确认。人员以 `assignee`、`git config user.name` 和当前分支为准，不把固定人员清单写入仓库。

有负责人时 `assignee` 恰好一个。只有该负责人可以修改正文、`status`、`deps`、`links`、验收标准和 Notes。当前身份不是 assignee 时不直接编辑，改为：在 Gitee PR 或 fer 中评论；新建关联 ticket 并链接原票；或请用户先把 `assignee` 转交。转交时先改 `assignee`，再改内容，并在 Notes 记录原因、时间和原负责人。`assignee` 为空的票可先写入自己再修改。

地图票（`wayfinder:map`）的 Decisions so far 只由该地图的 assignee 更新。子票结论由子票 owner 写在子票里，再由地图 owner 转载索引。

编辑前重新读取该票。与他人结论冲突时不覆盖、不删除；在 Notes 追加带日期的修订，写明推翻哪一条、依据是什么，并保留原文。关闭、重开或拆分他人负责的票，按上面三种非直接编辑方式提出。

本节约定 ticket 文档的修改权，不约定代码归属。代码仍在 `feature/<开发者>` 分支上通过 PR 修改。`assignee` 是内容裁决人，不是唯一实现者；他人实现须经 assignee 同意，并把结果回写到该票。

## Git、Gitee 与变更日志

开始前查看：

- `git branch --show-current`
- `git status --short --branch`
- `git remote -v`

开发者身份必须能由当前分支 `feature/<开发者>` 确认。当前已有 `feature/qiyueran`、`feature/hefan`、`feature/zhanyunfei`。身份或目标分支不明确时先向用户确认，再改文件。只在对应的 `feature/<开发者>` 分支上开发。`develop` 是集成分支，`master` 是稳定分支；只通过合并或 PR 进入这两条分支。开始前检查是否包含最新 `develop`；需要同步时先说明操作，并保留用户未提交的修改。

远程是 Gitee：

- HTTPS：`https://gitee.com/qi-yueran/ai4science.git`
- SSH：`git@gitee.com:qi-yueran/ai4science.git`
- 常规读写：`origin`
- SSH 推送：`ssh_origin`，例如 `git push ssh_origin <branch>`
- 集成分支：`develop`

仓库协作和 Pull Request 使用 `gitee`（gitee-cli）。创建 PR 前确认当前分支是对应的 `feature/<开发者>`，且标题、正文和验证证据完整；目标分支为 `develop`，例如 `gitee pr create --base develop`。推送前确认远程名称、目标分支和待推送提交，不要把开发分支推到 `develop` 或 `master`。

受信任的个人环境可用 `git config --global credential.helper store` 保存 HTTPS 凭据。凭据以明文放在用户目录，不得提交凭据文件、令牌或密码。共享机器改用 SSH 或其他凭据方式。

每完成一个可验证的逻辑变更就提交，不积累无关修改。提交信息使用 Conventional Commits，例如 `feat(scope): add ...`、`fix(scope): correct ...`、`docs(scope): update ...`、`refactor(scope): simplify ...`、`test(scope): cover ...`、`chore(scope): maintain ...`。一个提交只表达一个目的，不把格式化、重命名和功能修改混在一起。提交前看 `git diff` 和 `git diff --cached`。提交后看 `git status`，并记录验证命令和结果。钩子失败时修正原因，不强制提交。

完成可审查的功能、需要合并到 `develop`，或用户明确要求时创建 PR。正文遵循 `pr` skill：变更摘要、验证证据、合并风险、影响范围，并引用 fer issue 或 spec。审查走 `code-review`；问题修复后再提交，并在 PR 中补充验证结果。合并、变基、重置或删除分支前确认工作区状态和目标，避免覆盖他人提交。

变更日志配置在根目录 `cliff.toml`。执行 git-cliff 前先读该配置，不在命令行覆盖分类规则。创建 PR、准备发布或用户要求更新日志时运行：

```bash
git cliff --config cliff.toml --output CHANGELOG.md
```

生成前确认提交范围、版本标签和工作区状态，不把未确认的临时提交或其他开发者分支写入发布日志。确认内容后把 `CHANGELOG.md` 与对应变更一起提交。配置未声明输出文件时显式使用 `--output CHANGELOG.md`。
