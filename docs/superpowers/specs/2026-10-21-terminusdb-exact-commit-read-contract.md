# TerminusDB 12.0.8 精确 Commit 读取契约

- 日期：2026-10-21
- 关联工单：[`ai4-mqtq`](../../../.tickets/ai4-mqtq.md)、[`ai4-vczt`](../../../.tickets/ai4-vczt.md)
- 状态：源码级契约与本机真实服务端到端读回均已确认（2026-10-21）

## 目的

Research Mapping 与 LLM-Wiki 的 Formal Query 都必须按 Formal Revision 记录的精确 `store/branch/commit` 读回图内容，不允许按 branch 名称或“最新 Commit”推断。本文件固定 TerminusDB 12.0.8 上这条读取路径的契约，作为 `TerminusStore.read_exact_snapshot(...)` 的实现与集成测试依据。

## 证据来源

| 证据 | 说明 |
| --- | --- |
| `terminusdb/terminusdb` 标签 `v12.0.8` 的 `src/server/routes.pl` | 路由注册 `api(document/Path)`，`prefix` + `methods([head,options,post,delete,get,put])` |
| 同标签 `src/core/util/data_version.pl` | `TerminusDB-Data-Version` 头解析与回写；取值 `branch:<head>` 或 `commit:<id>` |
| 同标签 `tests/lib/api/path.js` | `documentCommit` 构造 `/api/document/{org}/{db}/{remote}/commit/{commitId}` |
| 同标签 `tests/test/data-version.js` | 对 `/api/document/.../commit/...` 断言响应头回显 `commit:<id>`，且不匹配时报 `badDataVersion` |
| `dockers/service/terminusdb/compose.yaml` | 固定镜像 `terminusdb/terminusdb-server:v12.0.8`（Docker Hub 实际标签带 `v` 前缀） |
| 2026-10-21 本机容器实测 | `docker compose` 启动固定镜像后，对同一数据库的两个提交分别按 `commit:<hash>` 读取，历史提交只返回该时点的文档，branch head 返回包含后续文档的集合 |
| 2026-10-21 `llm-wiki` 集成用例 | 自建临时数据库写入 `Resource`/`ResourceVersion`，在后续提交更新同一版本后分别读取历史提交与 branch head，确认返回原值与更新值不同，且两者的快照 SHA-256 不同 |

`ai4-2alw`、`ai4-9hcj`、`ai4-2sdn` 已在该镜像上实测 branch、Commit、History、Diff、rebase 与只读归档；本文件补齐“按精确 Commit 读回内容”这一条，并已在 2026-10-21 用同一个固定镜像完成本机端到端读取。

## 契约

### 1. 读取精确 Commit 快照

```text
GET {base_url}/api/document/{store}/{database}/{remote}/commit/{commit_hash}?as_list=true&graph_type=instance
Accept: application/json
TerminusDB-Data-Version: commit:{commit_hash}
```

- `{store}` 由 Store 配置给出，对应 URL 中的组织段；本地验证使用默认组织，不在源码或测试中写死具体值。
- `{database}` 由 `SCIWEAVE_MAPPING_TERMINUSDB_DATABASE` / `SCIWEAVE_WIKI_TERMINUSDB_DATABASE` 提供。
- `{remote}` 是 TerminusDB Repository 的 remote 名称；实现通过构造参数传入，本地默认 `local`。
- 成功时响应体是文档列表；必须同时满足：HTTP 200、`content-type` 为 JSON、响应头 `TerminusDB-Data-Version` 等于 `commit:<commit_hash>`。
- `commit:<id>` 与 `branch:<head>` 是两种数据版本标签；读取历史必须使用 `commit:` 标签，否则服务端可能按当前 branch head 返回或直接报 `bad_data_version`。

### 2. 解析 Commit 身份

```text
GET {base_url}/api/log/{store}/{database}/{remote}/branch/{branch}?count={n}
```

每条记录的 `@id` 形如 `ValidCommit/<identifier>`（实测格式，不是 `commit/<identifier>`），`identifier` 字段就是 commit hash，`parent` 指向父提交；`author`、`message`、`timestamp` 用于审计。

### 2.1 鉴权

固定容器默认开启 JWT，但没有配置 JWKS/OIDC 密钥来源，因此任何 Bearer 令牌都会被拒；可用的是 HTTP Basic 的容器存储密钥凭据（默认 `admin:<store-key>`），匿名请求返回 403。适配器必须在二者之间显式选择：配置令牌时发送 `Authorization: Bearer`，配置用户名和密码时发送 `Authorization: Basic <base64(username:password)>`，不允许同时配置或凭据不完整。

### 3. 失败语义

| 情况 | 判定 |
| --- | --- |
| HTTP 200 且数据版本头等于请求 commit | `confirmed`，附带实际 store/database/branch/commit 身份 |
| HTTP 404，或错误体明确说明 commit/资源不存在 | `missing` |
| 连接失败、超时、5xx、响应不是 JSON、数据版本头缺失或与请求不符 | `unavailable`（不得当成成功或空快照） |

区分 `missing` 与 `unavailable` 是正式化恢复的要求：前者说明引用已失效需对账，后者说明当前无法证明，两者都不能让 Formal Query 返回候选内容。

### 4. Wiki 精确 ResourceVersion 读取

`ResourceVersion` 是不可变文档，但版本 ID 本身不能定位历史提交。读取契约因此是：

```text
read_resource_version(location, resource_version_id)
location = ResourceVersionLocation(store_id, database, branch_id, commit_hash)
```

- `location` 必须来自写入该版本时固定的治理记录（候选或正式快照写入时保存），不能由版本 ID 反查，也不能用 branch 名称替代。
- 读取复用上面的精确 Commit 文档路由；`branch_id` 作为身份的一部分记录，但不参与 URL 解析。
- 只有同时满足以下条件才是 `confirmed`：HTTP 200、JSON 响应、数据版本头等于 `commit:<location.commit_hash>`、返回文档列表中恰好一个文档匹配 `resource_version_id`（字段或 `@id` 后缀）。
- 确认结果包含精确目标 ID、所属 Resource、`owner_id`、声明的 `content_checksum_value`，以及对匹配文档按规范 JSON 计算的快照 SHA-256。快照摘要与版本声明的校验和是两类证据，不能互相替代。
- 返回文档中没有该版本 ID 时是 `missing`；未知 commit 在本镜像上是 500，按 `unavailable` 处理；未知位置不允许发起读取，直接 `unavailable` / `exact_version_location_unknown`。

**当前范围：** Wiki 的候选/正式快照写入尚在后续切片；本切片只固定读取 seam，并要求调用方注入 `ExactVersionLocationSource`。没有位置记录时服务失败关闭，不批准任何版本。

**实测限制（2026-10-21）：** 固定镜像对未知 commit 在文档路由和日志路由上都返回 `500 api:InternalServerError`，而不是 404 或明确的不存在错误体。因此在这个版本上无法仅凭响应区分“缺失”与“服务故障”，适配器只能返回 `unavailable`。`missing` 仅保留给能给出 404 或明确不存在错误体的实现，不得靠猜测 500 的成因来归类。

## 本机端到端验证（2026-10-21）

固定镜像 `terminusdb/terminusdb-server:v12.0.8` 在本机启动成功，实测结果：

- 精确 Commit 读取返回 200，响应头回显 `commit:<请求 hash>`，正文只包含该时点的文档。
- 同一数据库的历史提交与 branch head 返回不同的文档集合，证明读取没有回退到最新版本。
- 未知 commit 返回 500（见上文限制）。
- `research-mapping` 的 3 个集成用例在真实服务上通过，`uv sync --locked` 与全部 36 个测试通过。
- `llm-wiki` 的 5 个集成用例在真实服务上通过：测试创建临时数据库，写入 `Resource` 与 `ResourceVersion`，记录历史提交，再更新同一版本的许可字段生成新的 branch head。历史提交读回原许可与对应的快照摘要，branch head 读回更新后的值，证明读取没有回退；未知版本在可读提交上返回 `missing`，未知提交返回 `unavailable`。全量 46 个测试通过。

镜像与数据准备步骤见 `dockers/service/terminusdb/README.md`。

仍然有效的约束：

1. `research-mapping` 与 `llm-wiki` 的集成测试必须显式开启；服务或配置缺失时记录为阻塞或跳过，不能记为通过。
2. 适配器对未知响应一律返回 `unavailable`，禁止根据“200 但结构不符”构造成功结果；不得为了让测试变绿而放宽 `confirmed` 的判定条件。
3. Wiki 的精确版本读取已补齐为 `read_resource_version(location, resource_version_id)`：位置必须来自固定写入的治理记录，版本 ID 只用于在同一 Commit 的文档集合中选取目标。实现不得退回到“只拿版本 ID 解析路径”或 branch head；写入侧切片落地前，服务因缺少位置记录而失败关闭。
