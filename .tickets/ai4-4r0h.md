---
id: ai4-4r0h
status: closed
deps: []
links: [ai4-grlc, ai4-tj83, ai4-4zjz]
created: 2026-10-27T10:19:33Z
type: bug
priority: 1
assignee: Frank Qi
tags: [toolkit, task-agent, config, dx, ready-for-agent]
---
# 套件出厂配置的一致性与可加载性

套件「拿到就能装就能跑」这条线上，配置层还有一批彼此关联的缺口。它们的共同点是：**代码能加载、测试全绿，但研究员照 README 做出来的东西是空的**。本票只修配置层，不实现 fast-agent 真实调用。

与 [ai4-grlc](ai4-grlc.md) 的关系：那张票只留 session 目录转义这一条红测试，配置相关的四项挪到本票，因为它们的根因是同一件事——出厂配置没有「加载出来是不是有用」的验收。

## 一、Agent 定义文件加载出来是空的，而且不报错

`agent-definitions/agents/` 下四个文件是**扁平的单 agent 定义**，没有 `agents:` 顶层包裹：

```
$ head -3 agent-definitions/agents/biology-collaborator.yaml
name: biology-collaborator
identity: ...
instruction: ...
```

而 `load_workflow_yaml` 要求顶层有 `agents:` 与 `workflows:` 两段，于是按目录加载时两段都不存在：

```
$ PYTHONPATH=runtime/src python3 -c "from work_agent_runtime.config import load_workflow_yaml; c=load_workflow_yaml('agent-definitions/agents/'); print('agents:', len(c.agents), 'workflows:', len(c.workflows))"
agents: 0 workflows: 0
```

**零个 agent，退出码 0，没有任何 warning。** 研究员把自己的 agent 放在这个目录里，`discover` 出来是空的，却不会收到任何提示。

要修的是两件事：给 `agent-definitions/agents/*.yaml` 补 `agents:` 包裹；以及让「目录里存在 `.yaml` 但解析出零个定义」成为稳定错误（而不是合法空结果），错误码建议 `no_definitions`。

顺带一处：`example-fast-agent.yaml` 缺 `identity` 字段，而 `AgentDefinition` 把它当必填（`_required()` 拒绝 `None` 与 `""`）。同一个目录下四个文件里有一个不符合自己声明的 schema，说明没有测试在跑这个目录。

## 二、四份 Workflow YAML 一字不差地存在两份

```
./agent-definitions/workflows/router-example.yaml         == ./libs/workflow-libs/router-example.yaml
./agent-definitions/workflows/orchestrator-example.yaml   == ./libs/workflow-libs/orchestrator-example.yaml
./agent-definitions/workflows/parallel-example.yaml       == ./libs/workflow-libs/parallel-example.yaml
./agent-definitions/workflows/agents-as-tools-example.yaml == ./libs/workflow-libs/agents-as-tools-example.yaml
```

`cmp` 逐字节相同，不是「长得像」。`README.md:7` 自己写着「`agent-definitions/`：兼容入口……可复用 Workflow 资源位于 `libs/workflow-libs/`」——既然可复用的那份在 `libs/`，`agent-definitions/workflows/` 这四份就是迁移（`ai4-s2nb`）后没清的残留。

改任意一份都不同步另一份，而「改哪份生效」取决于读者读的是 README 还是目录。收敛成一份，在 `agent-definitions/workflows/README.md` 留一句指路；**不要留软链**——套件要能打成 zip 发给别人的 Agent，软链解压后会坏。

## 二之二、收敛成一份也不够：四个示例的 agent 名互相冲突

这是比「重复两份」更硬的缺陷。`load_workflow_yaml` 按目录加载时，是把多个文件的 `agents` / `workflows` **合并**成一个命名空间，重名直接报错（`config.py` 的 `duplicate_definition`），不是覆盖。而四个示例各定义了一个叫 `writer` 的 agent，四份定义内容完全一致：

```
$ for f in libs/workflow-libs/*.yaml; do ... $f 的 agents.writer ...; done
agents-as-tools-example.yaml -> {'identity': 'final writer', 'instruction': 'write one draft', ...}
orchestrator-example.yaml    -> {'identity': 'final writer', 'instruction': 'write one draft', ...}
parallel-example.yaml        -> {'identity': 'final writer', 'instruction': 'write one draft', ...}
router-example.yaml          -> {'identity': 'final writer', 'instruction': 'write one draft', ...}
```

实测：

```
$ PYTHONPATH=runtime/src python3 -c "from work_agent_runtime.config import load_workflow_yaml; ...load_workflow_yaml('libs/workflow-libs/', ...)"
[duplicate_definition] config.agents: writer
```

**即使删掉 `agent-definitions/workflows/` 那四份重复，剩下四份仍然不能共存于同一目录。** 这就意味着 `WORKFLOW_LIBS_PATH` 一旦真的实现、指向 `libs/workflow-libs/`，启动即失败；而 `ai4-x0ay` 还要往这个目录里再加一个文献工作流，届时冲突只会更多。所以「一份 + 一个目录」这个目标本身是坏的，必须连命名一起改。

修法：**每个示例的 agent 名加文件级前缀**，让目录合并合法且能一眼看出归属。

| 文件 | 改名前 | 改名后 |
| --- | --- | --- |
| `router-example.yaml` | `router` / `searcher` / `writer` | `router` / `router-searcher` / `router-writer` |
| `orchestrator-example.yaml` | `orchestrator` / `researcher` / `writer` | `orchestrator` / `orchestrator-researcher` / `orchestrator-writer` |
| `parallel-example.yaml` | `coordinator` / `literature` / `mapping` / `writer` | `parallel` / `parallel-literature` / `parallel-mapping` / `parallel-writer` |
| `agents-as-tools-example.yaml` | `main` / `specialist` / `writer` | `a2t-main` / `a2t-specialist` / `a2t-writer` |

工作流名同理加前缀（现在四个工作流名分别是 `router-example` / `orchestrator-example` / `parallel-example` / `agents-as-tools-example`，已经不冲突，但 `writer` 冲突；把工作流名与 agent 名一起前缀化，规则更一致）。改完必须能跑通：

```
load_workflow_yaml('libs/workflow-libs/', known_mcp_resources=registry)
→ 4 个工作流、全部 agent 引用可解析
```

`ai4-x0ay` 的 `literature-agent.yaml` 也进这个目录，它的 agent 命名（`literature-searcher` / `mapping-reader` / `wiki-reader` / `draft-writer` / `literature-agent`）已经带领域前缀，天然不撞。

## 三、`WORKFLOW_LIBS_PATH` 只存在于 README

`README.md:25` 写：

> Agent、MCP、Workflow libs 是纯配置资源……由 runtime 通过 `AGENT_LIBS_PATH`、`MCP_LIBS_PATH`、`WORKFLOW_LIBS_PATH` 或显式路径加载。

前两个在代码里有实现（`resources.py:75`、`mcp_resources.py:57`），第三个**零实现**：全树 grep 只命中 README 那一行，`.env.example` 里也没有。

按设计轮次（2026-10-27）的结论，实现方式与另两个对齐：`WORKFLOW_LIBS_PATH` 指向标准目录，`LOCAL_WORKFLOW_LIBS_PATH` 指向研究员自定义目录，本地可覆盖标准——沿用 `ResourceRegistry` 已有的 `_add(resources, allow_override)` 语义，不要另造一套「冒号拼接多路径」。

同时 `AGENT_LIBS_PATH`、`MCP_LIBS_PATH`、`WORKFLOW_LIBS_PATH`、`LOCAL_AGENT_LIBS`、`LOCAL_MCP_LIBS`、`LOCAL_WORKFLOW_LIBS` 这六个变量 `.env.example` 里一个都没有（当前只有 `LOCAL_MCP_LIBS=` 一个，第 14 行）。

## 四、四类 Workflow 示例全部缺 `version` 字段

八个文件（两份各四个）没有一个写 `version:`，加载器因此全部落到默认值 `1.0.0`。`schema.yaml` 把 `version` 列为必填，`libs/workflow-libs/README.md` 的样例里也写着 `version: 1.0.0`。示例与自己的 schema 不一致，等于把「可以省略」教给研究员。

### `version` 的两个入口校验不一致，这一点要一并说明

`load_workflow_yaml` 会检查：

```python
version = data.get("version", "1.0.0")
if not isinstance(version, str) or not version.startswith("1."):
    raise ConfigError("unsupported_config_version", ...)
```

但 `load_config` **完全不看 `version`**。实测：

```
顶层 version: 1.0.0 → OK
顶层 version: 2.0.0 → OK（未校验）
无 version          → OK（默认值）
```

所以「补 `version: 1.0.0`」只对走目录/文件加载的路径有意义；直接调 `load_config` 的调用方（测试、未来的装配代码）拿着 `2.0.0` 也能过。本票不强制把校验搬进 `load_config`（它是纯 mapping 校验层，不该关心文档版本），但要在 `schema.yaml` 与协议文档里写明：**`version` 只在文件/目录加载路径上被强制**，并补一条测试固化这个分工。

另外这八个文件全部需要传 `known_mcp_resources` 才能加载，否则报 `[unknown_mcp_resource]`——这是正确行为，但没有任何测试固化「配了 MCP registry 之后能加载」这件事，于是 `ai4-tj83` 改动卡片工具面时不会有任何回归保护。

## 四之二、未知键被静默丢弃

`load_config` 逐字段取值，多出来的键直接消失，不报错：

```
$ load_config({... workflows: {w: {...合法字段..., bogus_key: 123}}})
bogus_key 保住了吗: False
```

顶层也一样：`{'agents':..., 'workflows':..., 'unknown_top': 1}` 能正常加载。agent 段同理（`AgentDefinition` 只读 8 个键）。

这与第一条的 `no_definitions` 是同一个病根：**YAML 里写了不生效的东西，却没有任何提示**。研究员照 fast-agent 文档写了 `plan_type`，配置能加载、能跑，就是那个参数从来没生效过（`ai4-x0ay` 已经踩了这一脚）。

修法：`load_config` 对 `agents.<name>`、`workflows.<name>` 与顶层三处做白名单校验，多出的键报 `unknown_field`。合法键集合以 `AgentDefinition` / `WorkflowDefinition` 的字段为准，加上已知别名（`allowed_domain_mcps` / `children`）。注意这是**向后不兼容**的收紧——仓库内现有 YAML 实测无多余键（`libs/workflow-libs/*.yaml` 四个文件的 agent 段与 workflow 段都是干净的），所以现在就收紧成本最低。

`ai4-x0ay` 会新增 `plan_type` / `plan_iterations` 两个合法字段，两票落地顺序不分先后，但**后落地的一方必须把新字段加进白名单**，否则会把对方写好的配置判成 `unknown_field`。

## 五、`.env.example` 的缺项与重复

| 变量 | 代码里的用法 | `.env.example` |
| --- | --- | --- |
| `SCIWEAVE_AGENT_ID` | `required`，订阅端与 worker 都读 | **缺** |
| `SCIWEAVE_SUBSCRIBER_TOPICS` | `required`，缺了直接 `SystemExit` | **缺** |
| `WORKFLOW_LIBS_PATH` / `LOCAL_WORKFLOW_LIBS_PATH` | 见第三条 | **缺** |
| `AGENT_LIBS_PATH` / `LOCAL_AGENT_LIBS` | `resources.py` | **缺** |
| `MCP_LIBS_PATH` | `mcp_resources.py:57` | **缺** |
| `LITERATURE_MCP_PROJECT_DIR` | 新卡的 `project_dir_env` | **缺**（随 `ai4-cxnm` 落地后补） |
| `DRAFT_BUFFER_MCP_TOKEN` | 第 12 行与第 19 行**重复两行** | 删第 19 行 |

`OPENAI__API_KEY` / `OPENAI__BASE_URL` 看起来也缺，但**不该补**：它们由 `fast_agent_runtime.py:93-98` 在每次调用前从 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` 派生写入，原文只是保存与还原现场。写进 `.env.example` 会误导研究员以为要单独配一份 OpenAI 凭据。

## Acceptance Criteria

- [x] `agent-definitions/agents/*.yaml` 全部带 `agents:` 顶层包裹；四个文件都能被 `load_workflow_yaml` 解析出非空 `agents`。
- [x] 目录里存在 `.yaml` 但解析出零个 agent/工作流时返回稳定错误 `no_definitions`，不再静默返回空配置；补测试覆盖。
- [x] `example-fast-agent.yaml` 补 `identity`，与该目录声明的 schema 一致。
- [x] 四份重复的 Workflow YAML 收敛为 `libs/workflow-libs/` 一份，`agent-definitions/workflows/` 只留指路说明，不使用软链。
- [x] 四个示例的 agent 名按第二节之二的前缀表改名（`writer` → `router-writer` / `orchestrator-writer` / `parallel-writer` / `a2t-writer` 等），工作流名与 `entry_agent` / `sub_agents` / `summarizer` / `final_writer` / `tools` 引用同步更新。
- [x] 新增测试：`load_workflow_yaml('libs/workflow-libs/', known_mcp_resources=<真实 registry>)` 一次加载整个目录成功，返回 4 个工作流且全部引用可解析——这条在改名前必红，是第二节之二的回归保护。
- [x] 实现 `WORKFLOW_LIBS_PATH` 与 `LOCAL_WORKFLOW_LIBS_PATH`：标准目录加载 + 本地覆盖，语义与 `AGENT_LIBS_PATH` / `LOCAL_AGENT_LIBS` 一致，并补测试。
- [x] 八个 Workflow YAML 全部补 `version: 1.0.0`。
- [x] `load_config` 对顶层、`agents.<name>`、`workflows.<name>` 三处做键白名单校验，多余键报 `unknown_field`；补测试覆盖三处各一例，并确认仓库内现有 YAML 全部仍能加载。
- [x] `schema.yaml` 与协议文档写明「`version` 只在文件/目录加载路径强制，`load_config` 不校验」，并补测试固化该分工。
- [x] 新增测试：把 `libs/workflow-libs/` 与 `libs/mcp-libs/` 一起加载，四类工作流全部通过校验（固化「配了 registry 就能加载」这条契约）。
- [x] `.env.example` 补齐 `SCIWEAVE_AGENT_ID`、`SCIWEAVE_SUBSCRIBER_TOPICS`、六个 libs 路径变量，删掉重复的 `DRAFT_BUFFER_MCP_TOKEN`，每个新变量各带一行说明。
- [x] 照 `.env.example` 填最小值即可启动 `gateway/subscriber`，不再停在「缺必填变量」。
- [x] runtime 全量测试通过；`compileall` 与 `git diff --check` 通过。

## Not in Scope

- 不实现 fast-agent 真实调用链路（`Forward` 到 `ai4-g1km`），本票只保证配置能正确加载。
- 不改 `mcp_resources.py:37` 的 `unsafe_startup` 白名单。
- 不动卡片工具面与权限切分（`ai4-tj83`）。
- 不评审 zip 打包与安装脚本，那是 wayfinder 地图的范围。
- 不补 worker 处置面契约差异（`answer_question` / `review_execution` 的幂等键与 resume 链），那需要先定研究员侧重放语义。

## Notes

**2026-10-27 立项（Frank Qi）**

> *This was generated by AI during triage.*

身份核对：assignee `Frank Qi`、分支 `feature/frank-qi`、`git config user.name=Frank Qi`，三者一致。

本票承接 `ai4-grlc` 的拆分决定：那张票降为「只装 session 目录转义那个 P1 红测试」，配置相关四项挪到这里，因为它们的根因是同一件事——出厂配置从来没有「加载出来是不是有用」的验收。

条款一、二、三、四都是 2026-10-27 实测的：`load_workflow_yaml('agent-definitions/agents/')` 返回 `agents: 0 workflows: 0` 且退出码 0；`cmp` 逐字节比对四对文件全部相同；`grep -rn WORKFLOW_LIBS_PATH` 全树只有 `README.md:25` 一行；`grep -L '^version:'` 命中全部八个 Workflow 文件。

与 `ai4-sxpw` 不重复：那张票已经关闭，交付的是 YAML 协议的读取与校验；本票修的是「协议有了，出厂配置却没按协议写全」。

**2026-10-27 复核修订（Frank Qi）**

> *This was generated by AI during triage.*

同日 grill 复审开了两处口子，原文都低估了：

6. **「收敛成一份」解决不了目录加载。** 原第二条把八份文件的问题描述成「重复两份」，实际四个示例各定义了一个 `writer` agent，按目录合并必然 `[duplicate_definition] config.agents: writer`。补第二条之二（改名前缀表）与两条 AC（改名 + 目录整体加载测试）。这条也直接决定 `WORKFLOW_LIBS_PATH` 能不能真的可用：目录加载不了的路径变量等于没有。
7. **未知键静默丢弃。** 原票只治「解析出零个定义」，没治「解析出来了但字段没用上」。补第四之二：三处键白名单 + `unknown_field`，并写明它与 `ai4-x0ay` 新增字段的先后顺序约定。`version` 两个入口校验不一致也一并记入第四条。

第二、四两条原文仍成立（`cmp` 逐字节相同、八个文件全缺 `version`），这里只补遗漏，不推翻原文。

**2026-10-27 完成（Frank Qi）**

> *This was generated by AI during triage.*

三个提交，按「一个提交一个目的」拆开：

- `2f03191 fix(toolkit): make the shipped config actually load as one directory` — 第一、二、二之二、三、四、四之二、五条；
- `aad4f2a fix(toolkit): close three drifts between the kit and its own spec` — 与本票第五节重叠的 `.env.example` 说明，以及 `ai4-4zjz` 的另两处（详见该票）；
- `664db9f fix(toolkit): make `cp .env.example .env` enough to start the subscriber` — 第五节最后一条 AC。

几处实现与原方案的偏差，都记在这里：

1. **`unknown_field` 的触发条件收窄了。** 最初把顶层键校验放进 `_read_documents`，结果扁平单 agent 文件（`name:` 写在顶层）报的是 `unknown_field: identity, instruction, model`——对研究员来说这条信息毫无用处，他真正的问题是「忘了 `agents:` 包裹」。现在顶层键校验只在文档里出现 `agents` 或 `workflows` 时才做，扁平文件继续报 `no_definitions`。这是本票最重要的一条设计取舍，测试里两个用例分别钉住两种输入。
2. **`LOCAL_WORKFLOW_LIBS` 与 `LOCAL_WORKFLOW_LIBS_PATH` 都认。** 票里只要求 `LOCAL_WORKFLOW_LIBS_PATH`，但相邻两个 registry 用的是 `LOCAL_AGENT_LIBS` / `LOCAL_MCP_LIBS`（无 `_PATH` 后缀）。两个都读，`.env.example` 只文档化带后缀的那个，避免研究员在三个 `LOCAL_*` 变量之间猜命名规则。
3. **第八条 AC 的「八个文件」实际只有四个。** 第二节收掉重复目录之后，需要补 `version` 的文件从八个变成四个。四份 `libs/workflow-libs/*.yaml` 全部补了 `version: 1.0.0`，并加了 `BundledConfigTests.test_every_shipped_example_declares_its_version` 逐文件断言，防止以后新增示例漏写。
4. **`.env.example` 的库路径变量改用分组注释而非行尾注释。** 行尾 `#` 在部分 env-file 解析器里会被并进值里，`AGENT_LIBS_PATH=  # shipped` 会变成一个带空格和井号的路径。改成每组上方一行注释。
5. **`.env.example` 里 `SCIWEAVE_AGENT_ID` / `SCIWEAVE_SUBSCRIBER_TOPICS` 填了默认值**（`researcher-task-agent` 与其对应 topic），不是留空。留空的话「照 `.env.example` 填最小值即可启动」这条 AC 仍不成立，因为 `required()` 会直接 `SystemExit`。填默认值 + 注释「按自己的 agent id 改这两行」才真的可启动。

验证（都在提交前跑过）：

```
load_workflow_yaml('agent-definitions/agents', known_mcp_resources=<5 张真卡>)
→ agents: biology-collaborator / data-collaborator / materials-collaborator / researcher-task-agent
load_workflow_libs(standard_path='libs/workflow-libs', ...)
→ agents: 13, workflows: agents-as-tools-example / orchestrator-example / parallel-example / router-example
```

- runtime 全量 129 条通过；
- `.env.example` 原样载入环境后调 `build_runtime()`：`agent_id: researcher-task-agent`、`topics: sciweave.task-handoff.researcher-task-agent`、`drafts: FakeDraftBox`；
- `compileall` 与 `git diff --check` 干净。

一处留给后人的注意：`load_config` 现在是键白名单，`ai4-x0ay` 会新增 `plan_type` / `plan_iterations` 两个合法字段。那张票落地时必须同步把它们加进 `config.py` 的 `_WORKFLOW_KEYS` / `_AGENT_KEYS`，否则会把写好的配置判成 `unknown_field`。这条原票已提醒，这里再钉一次。
