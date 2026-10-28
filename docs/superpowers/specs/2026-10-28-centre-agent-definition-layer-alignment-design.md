# 中央 Agent 定义层与目录结构对齐 Task Agent 模板

- 日期：2026-10-28
- 关联工单：`ai4-yidf`（父票）；本规格取代 [`2026-10-28-centre-agent-runtime-template-port-design.md`](2026-10-28-centre-agent-runtime-template-port-design.md) 中「卡片留在套件、中央侧不复制」的落地位置决策，其余决策继续有效
- 上游决策：[`ai4-fv1r`](../../../.tickets/ai4-fv1r.md)（中央 Agent 只做候选预审）、[`ai4-he04`](../../../.tickets/ai4-he04.md)（入口只走领域管理 MCP 只读候选工具）、[`ai4-a2ba`](../../../.tickets/ai4-a2ba.md)（事件触发与去抖）
- 约束：[ADR-0002](../../adr/0002-work-agent-two-codebases.md)（两份源码，不抽共享库）、[ADR-0006](../../adr/0006-centre-single-container.md)（中央侧单容器多进程）
- 状态：施工前规格，供拆票使用

## Problem Statement

中央 Agent 和 Task Agent 都是 Work Agent 的实例，但两者的**描述层**已经长成了两种东西。

Task Agent 那边，`deploy-task-agent/` 是一个能交付的套件：`agent-definitions/` 里有 YAML 定义和 schema，`libs/mcp-libs/` 里有 MCP 卡片，`libs/workflow-libs/` 里有多 Agent 工作流的预设，`install.sh` 把它们装到目标目录，`check.sh` 检查它们齐不齐。改一次预审口径就是改一段 YAML。

中央 Agent 这边，同一个角色却是另一副样子：

1. **没有定义层。** 预审的指令是 `runtime.py` 里一句硬编码的 `"You are a SciWeave Task Agent Worker. Complete the owner's command concisely."`。这句话既没说预审，也没说不能批准候选。想调口径必须改 Python 并重新构建镜像。
2. **没有地方表达「一个工作流」。** 中央 Agent 干的是一串有先后的事——取快照、核分支事实、判冲突、写结论、发通知——但代码里只有一个 agent，这一串只能靠 prompt 里的自然语言暗示。`@fast.chain` 能表达它，却没有可加载的载体。
3. **卡片和源码分居两个仓库目录。** 五张卡片在 `toolkits/centre-agent-toolkit/mcp/`，`suite.yaml` 指 `mcp/<name>/mcp.json`；但卡片描述的是服务的能力，跟着套件走就意味着跟着「发给研究员的一套配置」走。中央 Agent 是装在服务器上的一个服务，它的能力描述应当与它同源。
4. **判据版本没有落地文件。** 报告必须带 `rule_set_version`，领域 MCP 必须能在 `SCIWEAVE_*_PREREVIEW_RULES_DIR` 下解析到 `<version>.json`。仓库里没有任何一份这样的文件，`centre-stack` 也没有配这两个变量。也就是说按现有代码，任何一次 `append_prereview_log` 都会被拒成 `rule_set_missing`。

后果不是「结构不够漂亮」，是这条链在真实部署里跑不通，而且改一次预审口径要动代码。

## Solution

按 Task Agent 模板的**描述层**给中央侧补齐同样的形状，源码仍然两侧分开（ADR-0002）：

```
centre-agents/
├── definitions/          # 一批 YAML：agents + workflows
│   ├── centre-prereview.yaml
│   └── schema.yaml
├── libs/
│   └── mcp-libs/         # 五张 MCP 卡片
├── rules/
│   └── 1.0.0.json        # 预审判据版本
├── gateway/{mcp,ingest,subscriber}/
└── worker/
```

四件事一起做：

- **定义层落地。** 五个 agent 和一个 `Chain` 工作流写在一份 YAML 里，模型、指令、允许的 MCP 资源和工具白名单都在里面。`worker` 启动时加载它，按声明注册 agent 与 chain。硬编码的指令串删掉。
- **卡片进 `libs/mcp-libs/`。** 与 Task Agent 同形状；卡片随源码一起进镜像，不再靠环境变量指回 toolkit。
- **判据版本落地。** `rules/1.0.0.json` 进仓库，`centre-stack` 把两个 `SCIWEAVE_*_PREREVIEW_RULES_DIR` 指向它。
- **套件侧退场。** `toolkits/centre-agent-toolkit/` 不再持有卡片；`suite.yaml` 的 `mcp:` 段删掉而不是留下一堆悬空路径。

搬的是**描述层的形状**，不是把套件的运行时包搬过来。

## User Stories

1. 作为维护者，我想把预审的口径写在一份 YAML 里，这样调整判据不需要改 Python、不需要重新构建镜像。
2. 作为维护者，我想让五个预审角色的模型与指令分别可配，这样核事实的那几个可以配便宜模型，写结论的配强模型。
3. 作为维护者，我想在 YAML 里声明「这一轮先取快照、再核事实、再判冲突、再写结论、最后发通知」，这样这一串顺序是配置而不是 prompt 里的暗示。
4. 作为维护者，我想让加载层在 Agent 声明了不存在的 MCP 资源时启动就失败，这样拼错卡片名不会变成「模型少几个工具」。
5. 作为维护者，我想让加载层在定义文件缺失或格式不对时启动就失败，这样不会有回退到内置指令的静默路径。
6. 作为维护者，我想让 Agent 的工具白名单写在定义里，这样取快照的角色只有两个读工具，写不了日志。
7. 作为维护者，我想让预审判据的版本文件进仓库并受 Git 版本化，这样「同一批候选在不同判据下得出无法比较的结论」可以避免。
8. 作为维护者，我想让部署配置把判据目录指向仓库里那份 `rules/`，这样报告里的 `rule_set_version` 能被领域 MCP 解析到。
9. 作为维护者，我想让卡片跟着源码进镜像，这样不再有「卡片在 toolkit、运行时在 centre-agents、中间靠一个环境变量连着」的脆弱结构。
10. 作为维护者，我想让中央侧不再被描述成一个套件，这样「给机器用的一套配置」和「装在服务器上的一个服务」不会再混淆。
11. 作为运维者，我想在启动时就看到缺哪个环境变量、哪张卡、哪个目录，这样一次部署失败只需要看一行错误。
12. 作为运维者，我想让 MCP 服务器的 URL 与令牌仍然只从环境变量来，这样 YAML 里不会有凭据。
13. 作为运维者，我想在 `centre-stack` 里看到判据目录被显式配置，这样「镜像里少一个文件」在启动时暴露而不是在第一次追加日志时暴露。
14. 作为运维者，我想让静态校验在卡片里出现 `formalize` 类工具时失败，这样能力上限仍然由测试守着，不靠人记得。
15. 作为 Project Owner，我想在候选被创建后看到一条真的基于领域工具的预审结论，这样我不必去猜中央 Agent 是不是还活着。
16. 作为 Project Owner，我想让通知只在结论落进日志之后发出，这样我不会收到一条「已预审」但日志里查不到的提醒。
17. 作为评审者，我想让每项改动都有一条只断言外部行为的测试——给一份定义、给一组环境变量，看框架收到的参数和生成的文件——这样重构实现时测试不跟着改。
18. 作为评审者，我想看到框架真的收到了 `servers=`、`tools=`、`skills=[]` 和 `@fast.chain(sequence=...)`，这样「声明了但没接线」这类缺陷不会再被中间层掩盖。
19. 作为评审者，我想让「改了 YAML 里的指令能改变框架收到的指令」被一条测试钉住，这样定义层不会退化成装饰。
20. 作为评审者，我想让判据文件的存在性被一条测试钉住，这样删掉 `rules/1.0.0.json` 不会静默通过。
21. 作为研究员，我想让中央侧这次改动完全不碰我机器上的 `deploy-task-agent`，这样我的 Task Agent 不因为中央预审换结构而失效。

## Implementation Decisions

### 采用描述层，放弃 AgentCard 文件

部署模板有两条互斥的路：一条是 fast-agent 自己的 AgentCard YAML，一条是「YAML 只做描述、代码做翻译」。本规格选后者，理由是可扩展：以后要加第二个 workflow、要给某个 agent 换模型、要按域名分不同的预审口径，都在同一份 YAML 里加段，不需要引入第二种文件格式和它的加载器。

同一件事只能有一个真相。因此这次不引入 AgentCard，也不保留「YAML 定义 + AgentCard」并存。

### 目录结构

`definitions/` 一个目录、一份定义文件。五个 agent 和一个 workflow 写在同一个文件里，因为它们互相引用，拆开只会让人来回跳。文件级前缀不需要——目前只有这一个工作流，名字已经带 `centre-prereview-` 前缀；以后加文件时这个约定也不用改。

`libs/mcp-libs/` 只是把卡片的目录名对齐部署模板。卡片内容不变，名字不变。

`rules/` 是中央侧独有的一层，部署模板没有对应物：它装的是预审判据版本，供**领域 MCP** 读取，不是给 Agent 读的。

`worker/` 暂不拆出独立的 `runtime/` 子项目。加载层放进 `worker` 包，因为 `gateway/mcp` 与 `gateway/subscriber` 已经通过 uv workspace 依赖它；新建一个 workspace 成员会改 `centre-stack/supervisord.conf` 里所有 console script 的路径，而这一步和本规格要解决的问题无关。

### 定义格式：v1 + Chain 扩展

沿用部署模板 `schema.yaml` 的词汇（`version` / `agents` / `workflows`，agent 的 `identity` / `instruction` / `model` / `allowed_mcp_resources` / `resources` / `references`），加两样东西：

1. 工作流类型多一个 `Chain`；
2. agent 多一个 `allowed_tools`：`{服务器名: [工具名, ...]}`，翻成 fast-agent 的 `tools=` 参数（每服务器工具白名单）。

不沿用部署模板的 `tools`（在那里它的含义是「Agents as Tools 的子 agent 列表」）。同一个键在两个代码库里表示两种东西，是下一次读代码的人一定会踩的坑；宁可多一个键名。

部署模板的四种类型（Router / Orchestrator / Parallel / Agents as Tools）都描述「谁去调谁」，需要 `entry_agent` / `sub_agents` / `summarizer` / `final_writer` 四个字段。预审这一串没有分派、没有并行、没有循环：它就是按顺序往下走。硬套 Router 会得到一个假的「路由」，硬套 Orchestrator 会得到一次自由的重新规划——而重新规划会再调一次 `list_reviewable_candidates`，把「同一时点快照」这个前提打破，这正是冲突判定要防的事。

因此 `Chain` 只要求 `sequence`（非空、按执行顺序）与可选 `cumulative`（默认 `true`，后者能看到前者的输出）。`entry_agent` 取 `sequence[0]`，`summarizer` 与 `final_writer` 取 `sequence[-1]`——这三个字段不写进 YAML，由加载层推导。这样部署模板那边的校验语义（三个字段必填、且必须指向已声明的 agent）在我们的形状里同样成立，只是值由顺序决定而不是由人填。

`version` 强制为 `1.x`，与部署模板一致。非 `1.x` 报错，不尝试兼容。

### 五个角色与它们的能力面

| agent | 允许的 MCP 资源 | 工具白名单 | 为什么 |
| --- | --- | --- | --- |
| `centre-prereview-intake` | `research-mapping`、`research-wiki` | `list_reviewable_candidates` / `get_formal_mapping`；`list_reviewable_wiki_candidates` / `get_formal_wiki` | 只取快照与正式版本，一次调用出一批 |
| `centre-prereview-audit` | — | — | 核对 head、基座、来源、快照是否可读，输入已在上下文里 |
| `centre-prereview-conflict` | — | — | 同批候选在同一逻辑对象上的重叠，输入已在上下文里 |
| `centre-prereview-verdict` | — | — | 把四项检查写成 `checks` 与 `conflict_matrix`，不写日志 |
| `centre-prereview-writer` | `research-mapping`、`research-wiki`、`email-service` | `append_prereview_log`；`append_prereview_log`；`send_notification` | 只有它能写日志和发通知 |

分开的理由是可验证性：一个「既能取快照又能写日志」的单 agent 无法在配置层证明它没有在核事实之前就写结论。分成五个之后，写权限只在一个角色身上。

`writer` 在 Mapping 与 Wiki 上都有 `append_prereview_log`，但一次调用只写一个域——这条是领域侧的硬约束，不是提示词里的建议，因此不需要在定义里再表达一遍。

### 能力上限不靠定义层守

定义层能收紧，不能放开。卡片里不得出现 `formalize_candidate` / `formalize_wiki` / `decide_wiki_review` / `record_review` 这条，仍然由静态校验守，不因为「YAML 里只声明了读工具」就放松——模型看得到工具的完整描述，定义层写多窄都不改变卡片本身有什么。

### 加载层的形状

一个入口，返回运行一轮需要的一切：

```
环境变量 -> load_centre_config() -> CentreConfig -> fast-agent
```

`CentreConfig` 至少暴露：选中的工作流、该工作流的 agent 顺序、每个 agent 的定义、**MCP 卡片目录（路径，而不是重新解析 `paths` 里的字符串）**、以及把卡片翻成 `mcp.servers` 块的能力。

三个根目录另外以 `{变量名: 解析到的路径}` 的形式报告一次，用途只有一个：运维问「容器实际读的是哪个 `rules/`」时有个地方可查。它不参与任何判断。

加载是严格的，三条都硬失败而不是回退：

- 定义目录不存在、目录里没有 YAML、YAML 不是 `1.x`：报错并给出目录与规则名；
- agent 声明的 `allowed_mcp_resources` 不在卡片目录里：报错并给出两者名字；
- 选中的工作流名不存在、或 `sequence` 里有未声明的 agent：报错并列出现有名字。

回退到内置指令是这次要消灭的失败形态，所以任何一条都不能有默认值。

### 卡片到 `mcp.servers` 的翻译

三处翻译与部署模板一致，差异不是装饰：

| 卡片 | fast-agent | 说明 |
| --- | --- | --- |
| `transport: streamable-http` | `transport: http` | fast-agent 的字面类型是 `stdio` / `sse` / `http` |
| `endpoint.url_env` | `url` | 卡片给变量名，运行时需要值 |
| `startup.project_dir_env` | `cwd` | 同理 |

**缺变量是错误，不是跳过。** 一张卡被静默丢弃，等于这个 Agent 手里的工具比定义里写的少，而第一个症状是模型绕着它本该有的工具编话。错误里必须带变量名和卡片名。

中央侧这五张卡都是 `streamable-http`，因此只需前两行翻译；`stdio` 分支一并实现，因为卡片格式是共享词汇，不为当前只有五种取值就写死。

卡片里的 `environment` 只列变量名，不发凭据。令牌是否作为请求头传给 MCP 服务器，是另一个问题（见 Further Notes），本规格不在这里解决。

### 只发出声明的服务器

按 agent 的 `allowed_mcp_resources` 生成 `mcp.servers`，不多发一个。这是 `allowed_mcp_resources` 存在的全部意义：核事实的角色不该拿到 `append_prereview_log`。

一个声明了零个资源的 agent 得到空列表，不是「继承别处配置」。

### `skills` 必须显式传空

fast-agent 的 `skills` 参数默认是一个哨兵值，含义是「用上下文/全局技能」。不传这个参数，一个无人值守的中央 Worker 会去扫 home 目录拿技能——那是研究员机器的行为，不是服务器的行为。

因此所有 `@fast.agent(...)` 都必须显式传 `skills=[]`。这与部署模板传路径列表是同一条理由的两面。

### 模型的三处取值与优先级

`model` 在 agent 定义里必填。取值规则：

1. 写具体模型名（例如 `deepseek-chat`）：这个 agent 就用它。这是给「核事实的角色配便宜模型、写结论的配强模型」留的出口。
2. 写占位符 `configure-in-your-own-environment`（沿用部署模板的约定）：回退到 `SCIWEAVE_WORKER_MODEL`。
3. 两者都没有：启动时硬失败。

出厂定义全部写占位符。理由不是省事，而是 `SCIWEAVE_WORKER_MODEL` 已经是部署侧必经的一项（`validate_for_model_call` 要求它非空），`centre-stack` 也在设它。若出厂 YAML 写死具体模型名，那个环境变量立刻变成死配置，而「部署时改了没生效」是排障里最费时间的一类。因此：**环境变量是出厂默认，定义里的具体模型名是逐 agent 的例外**，两者不冲突。

### 工作流的选择

`SCIWEAVE_WORKFLOW` 选工作流，默认 `centre-prereview`。默认值是必要的：只有一个工作流时不该要求部署方再配一个变量；但一旦配了不存在的名字，必须硬失败而不是静默回落到默认。

### 判据版本

`rules/1.0.0.json` 至少含 `version` 与 `checks`（非空字符串列表），`checks` 的取值与四项检查同名。文件进 Git，与代码同一份历史。

**版本号从目录推断，但推断失败就硬失败。** 目录里恰好一份 `*.json` 时它就是要记的版本；多于一份时必须由 `CENTRE_PREREVIEW_RULE_SET_VERSION` 显式选定。不能「取最新的」：报告里只存版本字符串，静默挑一份会让历史报告无法比较，而那正是 `rule_set_missing` 想防的事。显式指定的版本在目录里不存在，同样报错并列出可用的几份。

**`rule_set_version` 由加载层注入指令，不写在 YAML 里。** `writer` 的 `instruction` 里写 `{{rule_set_version}}`，加载时替换成解析结果。理由：版本是部署事实，不是作者知识；写死在 YAML 里意味着重命名判据文件要改两处，而漏改的那一处只在线上表现为「报告写的版本领域侧解析不到」。指令里本来就有 JSON 花括号，因此只做精确 token 替换，不引入模板引擎。

领域 MCP 通过 `SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR` / `SCIWEAVE_WIKI_PREREVIEW_RULES_DIR` 读它，因此 `centre-stack` 的 compose 必须把这两个变量指向 `centre-agents/rules/`。这两个变量属于领域 MCP 的配置，不属于 Agent 的配置——放错层会让「改了 Agent 的判据」和「改了领域认可的判据」看起来是同一件事。

### 两个不显眼但必需的装饰器参数

- **`use_history=False`。** fast-agent 的 `@fast.agent` 默认记事；而在 `cumulative` 的 chain 里，一个带历史的子 agent 会看到上一轮的对话——上一轮的候选、上一轮的结论。预审是「本次快照的一次判决」，跨轮记忆会让它拿旧事实回答新问题。累积由 chain 负责（每步看得见本轮前序输出），不由历史负责。
- **`default=True`。** 只声明一条 chain 时它是这轮回合的入口；不写 `default` 就得靠调用方按名字取，而在这个进程里没有第二个候选人。

### 版本占位符的识别方式

`model` 的占位符按前缀 `configure-` 识别，不按精确串 `configure-in-your-own-environment`。部署模板的 workflow 示例用的是 `configure-locally`，同一个约定已经有两个写法；按前缀识别让「以后再写一个 configure-xxx」不需要改代码。其余情况一律当具体模型名。

### 套件侧退场

`toolkits/centre-agent-toolkit/` 保留 skills、`cron/prereview-sweep.sh`、`bin/`、`suite.yaml`、`install.sh`、`check.sh` 这些**面向部署**的内容，但不再持有 MCP 卡片：`suite.yaml` 的 `mcp:` 段整体删除，而不是留五条指向已移动文件的路径。

`suitecheck` 的 `suite_empty` 因此要从「`skills` 与 `mcp` 各查一次」改成「两者都空才算空」。这确实放宽了一条全局检查，所以必须同时保留收紧的那一半：只声明 skills、一张卡都没有的套件是合法形状，什么都不声明的仍然是错误。

这与「central Agent 不是一个套件」的判断一致：中央侧的能力描述（定义、卡片、判据）属于服务本身，跟着源码走；套件那边只剩「怎么把它装起来、怎么定期体检」。

## Testing Decisions

好的测试只断言外部行为：给一份定义目录和一组环境变量，看加载出来的配置；给一组卡片和环境变量，看生成的 `mcp.servers` 文本；给一个 fake 的 `fast_agent` 模块，看框架收到的 kwargs。不断言内部函数调用顺序，不 mock 被测模块自己。

五个测试面，都尽量取最高接缝：

1. **加载层**。`load_centre_config(environ, root=...)` 是最高接缝：一份最小定义目录 + 一组环境变量进，配置对象出。覆盖：正常加载、定义目录缺失、`version` 不是 `1.x`、声明了不存在的资源、`sequence` 里有未声明的 agent、`SCIWEAVE_WORKFLOW` 指向不存在的名字。先例是部署模板的 `test_assembly.py`。

2. **配置渲染**。给定卡片与变量，生成的 fast-agent 配置文本包含 `mcp.servers`，每张卡的 transport 与 url 正确；缺一个必填变量时抛错且错误里带变量名与卡片名；未声明的服务器不出现。先例是部署模板的 `test_mcp_servers.py`。

3. **框架收到的参数**。在 `sys.modules` 里装一个 `fast_agent` 替身，记录每次 `@fast.agent(...)` 与 `@fast.chain(...)` 的 kwargs，断言：`servers=` 等于该 agent 的声明、`tools=` 等于工具白名单、`skills=[]`、`model=` 来自定义、`instruction=` 来自定义且改 YAML 会改变它、`chain` 的 `sequence` 与顺序一致。先例是部署模板的 `fast_agent_doubles.py` 与 `test_fast_agent_runtime.py`。

4. **静态资产**。直接读仓库里的文件，不经过运行时：`libs/mcp-libs/` 的每张卡都能被加载、卡片里没有 `formalize` 类工具、`definitions/` 里每个 `allowed_mcp_resources` 都在卡片目录里、`rules/1.0.0.json` 满足 `resolve_rule_set` 的契约（`version` 相等且 `checks` 非空）。先例是部署模板的 `test_standard_mcp_cards.py`、`test_domain_card_permissions.py`。

5. **部署配置**。`centre-stack/compose.yaml` 里两个 `SCIWEAVE_*_PREREVIEW_RULES_DIR` 存在且指向 `rules/`。这一条是文本断言，不好看，但它守的是一个真实发生过的失败形态：文件在仓库里、部署里没有。

`rules/1.0.0.json` 的契约测试要直接调领域侧已有的 `resolve_rule_set`，不要另写一份校验——两份校验会漂移，而漂移的后果是「测试说没问题、线上报 `rule_set_missing`」。

## Out of Scope

- **`gateway/ingest` 进 `centre-stack`。** 它目前没有 supervisord 程序，因此「事件触发 → 执行记录」这条链在容器里没有入口。这是独立缺陷，另开票。
- **`create_merged_candidate` 的调用时机。** 卡片里有这个工具，本规格只保证它可达，不定义谁在什么时候调它（`ai4-8dgd`）。
- **给 Project Owner 的通知内容与失败重试。** `writer` 声明了 `send_notification`，通知正文怎么写在指令里说，投递失败后怎么重试不在本规格。
- **Worker 的子进程派发。** 现在订阅器内联跑运行时，改成显式子进程是 `ai4-e959`。
- **Worker 租约的过期时间。** `ai4-1aeg`。
- **MCP 令牌注入。** 卡片只列变量名，`*_MCP_TOKEN` 要不要变成请求头、由谁负责，属于鉴权面，见 Further Notes。
- **把五个技能的内容搬进定义。** `toolkits/centre-agent-toolkit/` 下的 `SKILL.md` 保留不动；定义里的五段 `instruction` 只写**这一步要做什么、能做什么、绝对不能做什么**。判据本身（四项检查各查什么）不搬进来，它属于 `rules/<version>.json` 与技能文本。

  需要说清一处：`skills=[]` 意味着这五个 `SKILL.md` 在运行时**不在模型的上下文里**。所以凡是模型不看到就会做错的事（`append_prereview_log` 的参数形状、一次只写一个域、先写日志再发通知），必须写在 `instruction` 里——那是这一段唯一能到达模型的地方。这与「把技能文本复制一份」是两件事：前者是不可省的运行时输入，后者是第二份真相。
- **`ADR-0002` 的修订。** 本规格按它执行（两份源码、不 path 依赖），只记录债务加重。
- **真实模型与真实令牌的端到端验证。** 本机没有可用的模型密钥与领域 MCP 令牌，交付物是「接缝接上且被测试钉住」。

## Further Notes

- **ADR-0002 的债务变重了。** 原判断是「Agent 定义、MCP 卡片只有套件需要」。现在两侧都需要定义加载、卡片翻译、配置渲染，而且**形态趋同**——同样是 `version` + `agents` + `workflows`，同样是卡片到 `mcp.servers` 的三处翻译。这次仍然复制而不抽共享库，但要如实记录：两份实现会继续收敛，总有一天要一次裁决——要么抽共享包并改 ADR，要么明确接受长期双份。这一次不夹带。
- **`ADR-0006` 与派发方式的表述不一致。** ADR-0006 的 Consequences 写「worker 角色不常驻，由 gateway 用 multiprocessing 拉起」，而「显式子进程」的决策方向正好相反。那句话是过时的，应当在改派发方式时一并更正，本规格不改 ADR。
- **卡片里的 `environment` 与令牌注入是两件事。** 部署模板的渲染器只写 `transport` 与 `url`，`*_MCP_TOKEN` 从头到尾没有变成请求头。这意味着「卡片列了令牌变量」目前只是一份声明，不是一条生效的鉴权路径。中央侧照抄这个形状，因此同样的问题会在中央侧复现。这条要在真机联调前单独处理，不要以为配了变量就带了鉴权。
- **卡片的能力收窄是这次改动的下限。** 卡片挪目录不等于可以放松：`formalize` 类工具不得出现在中央侧任何一张卡里，这条已有静态校验守着，改动后必须仍然通过。
- **`SCIWEAVE_WORKER_MODEL` 与定义里的 `model` 的关系必须只有一个读法**（见「模型的三处取值与优先级」）。若实现里出现「定义优先、但环境变量也覆盖」这种双写，会在第一次排障时变成两小时的困惑。
- **本机没有 `DEEPSEEK_API_KEY`。** 因此「模型真的按 Chain 顺序调了工具」只能在有人提供密钥后补一次真实验证；在此之前状态是「接缝已验证、真机未验证」，不得标记为已实现。
