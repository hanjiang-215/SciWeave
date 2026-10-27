# literature-search

研究员端文献检索 MCP：两个公开源（arXiv、Crossref），都不需要 key。

只开两个工具：

| 工具 | 用途 |
| --- | --- |
| `search` | 按关键词检索，`source` 选 `arxiv`（缺省）或 `crossref`，`limit` 上限 20 |
| `get_abstract` | 按 arXiv id 或 DOI 取单篇；`source` 缺省时按 id 形态推断 |

## 边界

- 只读公开元数据，不下载 PDF、不解析全文、不做引用图。
- 不接 Semantic Scholar / OpenAlex / Google Scholar：前者要 key，后两者有共享额度或反爬限制。
- `license` 为 `null` 表示**源没声明**，不是「公有领域」。arXiv 的公开 Atom API 完全不返回许可证元素（对 50 条分类查询与老式 id 都实测过），所以 arXiv 结果恒为 `null`；Crossref 有 `license[].URL` 时原样返回。
- 上游端点、超时与联系邮箱全部走环境变量，源码里没有硬编码地址。

## 安装与配置

```bash
cd sci-weave/toolkits/researcher-agent-toolkit/deploy-task-agent/custom-mcp/literature-search
uv sync
cp .env.example .env    # 全空也能跑；两项端点留空即用公开地址
```

| 变量 | 缺省 | 说明 |
| --- | --- | --- |
| `LITERATURE_ARXIV_ENDPOINT` | `https://export.arxiv.org/api/query` | 镜像部署时替换 |
| `LITERATURE_CROSSREF_ENDPOINT` | `https://api.crossref.org/works` | 同上 |
| `LITERATURE_CONTACT_EMAIL` | 空 | 写进 `User-Agent` 的 `mailto:`；Crossref 建议填写 |
| `LITERATURE_TIMEOUT_SECONDS` | `10` | 单次请求超时，取值 1–30 |

## 最小验证

```bash
# 单元测试：64 条，全部走 httpx.MockTransport 与固定响应体，不碰网络
uv run --with pytest python -m pytest tests -q

# 真实联网抽查（两个源各一次）
uv run python -c "
from literature_search import tools
from literature_search.config import LiteratureConfig
print(tools.call('search', {'query': 'transformer', 'source': 'arxiv', 'limit': 2}, LiteratureConfig.from_env())[:300])
print(tools.call('search', {'query': 'transformer', 'source': 'crossref', 'limit': 2}, LiteratureConfig.from_env())[:300])
"
```

## 错误码

调用不抛异常，一律返回 `{"error": {"code": "...", "message": "..."}}`：

| 码 | 含义 |
| --- | --- |
| `invalid_arguments` | 参数不合法（空查询、`limit` 越界、id 形态无法识别） |
| `unsupported_source` | `source` 不是 `arxiv` / `crossref` |
| `literature_not_found` | 上游 404，或 `get_abstract` 拿到空 feed |
| `literature_timeout` | 超过 `LITERATURE_TIMEOUT_SECONDS` 或 30 秒总预算 |
| `literature_unavailable` | 连接失败，或可重试的 5xx / 429 用尽重试 |
| `literature_request_rejected` | 其余 4xx，重试无意义 |
| `literature_bad_response` | 返回体不是预期的 Atom / JSON 结构 |
| `literature_internal` | 未预期异常；不泄漏内部细节 |

重试策略：可重试状态（408/425/429/5xx）与超时最多重试 2 次，总耗时不超过 30 秒；其余 4xx 立即失败。

## 注册

卡片在 `../../libs/mcp-libs/literature-search/mcp.json`，`startup` 必须与 `runtime/src/work_agent_runtime/mcp_resources.py` 的 stdio 白名单逐字一致。`tests/test_card.py` 双向钉住这个契约：卡片与 `src/main.py` 的工具集、必填字段、参数名、错误码全部比对，并检查白名单源码没被放宽。

`LITERATURE_MCP_PROJECT_DIR` 指向本目录，由卡片声明、由 runtime 在拉起 stdio 服务时使用。
