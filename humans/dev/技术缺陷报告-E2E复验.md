# AI4Sci / SciWeave 技术缺陷报告（基于本轮全链路 E2E 验证）

验证过程中在**运行中的真实代码**里定位并修复了 3 个**真实缺陷**，其中 2 个直接导致 Wiki 候选提交链路完全不可用、1 个导致 Mapping 候选提交对「集合字段顺序」敏感（真实数据极易触发）。

所有修复均已在源码中落地，并已重启角色加载、通过 17/17 E2E 复验。

---

## 缺陷 1（严重）：Wiki 候选提交 100% 失败 —— opener 调用参数不匹配

- 位置：`sci-weave/centre-control/research-wiki/src/llm_wiki/terminus_store.py`
- 现象：任何 `submit_wiki_candidate` 均返回 `result_unknown / store_result_unknown`，Wiki 治理链完全不可用。
- 根因：`TerminusDBWikiCandidateStore._request()` 调用
  `self._request_opener(method, url, headers, body, self.timeout)`（**5 个位置参数**），
  而 opener 的真实类型是 `Opener = Callable[[url, headers, timeout], ...]`（**3 参数、仅 GET**，见 `_urllib_opener`）。
  `__init__` 又把 `_request_opener` 默认设为该 3 参 opener（`self._request_opener = self._opener`），
  于是 `_request` 第一次调用（`_candidate_branches()` 的 `GET db?branches=true`）即抛
  `TypeError: _urllib_opener() takes 3 positional arguments but 5 were given`，
  被外层 `except Exception` 吞掉，统一返回 `store_result_unknown`。
- 为什么之前能工作：读路径（`read_exact_snapshot` / 其它 GET）都走 `self._opener(url, headers, timeout)`（3 参）正确；
  只有新增的 `_request`（需要任意 method + body）错误地复用了 3 参 opener。属回归性缺陷。
- 修复：`_request` 不再路由到 3 参 `_request_opener`，改为自行构造 `urllib.request.Request(method/body)` 并发送
  （与其内部已有的 fallback 逻辑一致）。GET 读路径仍走原 `_opener`，语义不变。

---

## 缺陷 2（严重）：Wiki 候选提交「写入成功但校验失败」—— 比较未忽略服务端补写的 `@id`

- 位置：
  - `research-wiki/src/llm_wiki/terminus_store.py` `_candidate_documents_match()`
  - `research-wiki/src/llm_wiki/candidate_submission.py` `_contains()`
- 现象：修完缺陷 1 后，TerminusDB 侧 branch/reset/POST 全部 200、文档已写入，但 `create_candidate_snapshot` 仍返回
  `unknown`（`submit` 报 `store_result_unknown` / `candidate_snapshot_unverified`）。
- 根因：TerminusDB 写入后会给文档补写 `@id`（如 `WikiRevision/wiki-rev-xxxx`），
  回读校验时把「回读文档」与「提交文档」做**整字典相等**比较，而提交文档没有 `@id`，
  差集恰为 `{"@id": [<服务端值>, null]}`，于是 `doc == wanted` 恒为 False → 校验失败。
  实测 diff 仅有 `@id` 一项不同（其余字段逐一致）。
- 修复：两处比较均在对比前**剥离 `@id`** 字段（按 `wiki_revision_id` / `reference_id` 定位后比较其余字段），
  使校验对服务端补写的 `@id` 免疫。

> 缺陷 1+2 联合修复后，`submit_wiki_candidate` → `confirmed`，Wiki 治理链恢复全绿（preview/merge/decide/formalize/query）。

---

## 缺陷 3（中）：Mapping 候选提交对「集合（Set）字段顺序」敏感

- 位置：`sci-weave/centre-control/research-map/src/research_mapping/terminus_store.py` `_contains_documents()`
- 现象：候选节点的 `acceptance_criteria / expected_outputs / required_evidence / executor_refs` 等
  `@type:Set` 字段，若**元素非字典序**提交，`submit_candidate` 返回 `result_unknown / store_result_unknown`；
  改为有序提交即 `confirmed`。真实科研数据（中文、任意书写顺序）极易触发。
- 根因：TerminusDB 将 Set 成员按**规范（排序）顺序**回读；`_reconcile` 用 `_contains_documents()` 做**整字典相等**比较，
  输入侧保持原始书写顺序，故 `by_id[doc["@id"]] == doc` 因成员顺序不同而失配 → 误判为 `unknown`。
  （注：`_reconcile` 内另有 `sha256(canonical_json(documents)) == digest` 自校验，因两侧同源不受影响。）
- 修复：`_contains_documents()` 对比前对两侧文档的**字符串列表字段做排序归一化**（`_normalize_set_fields`），
  使对 Set 成员顺序免疫；语义等价、不改变其它校验。

---

## 附：非缺陷但值得记录的观察

1. **email-service `/health` 返回 503**：未配置 SMTP 时的预期行为（服务端返回 `not_configured`），MCP 功能正常，非故障。
2. **看板任务投影未展示标题、logical_id 显示为版本号**：`/api/dashboard/snapshot` 的 task 投影中
   `logical_id` 呈现为 `v1` 一类、`title` 为空——仅影响展示层可读性，不影响治理/调度/E2E 结果，建议后续看板投影补全字段。
3. **候选分支累积**：每次候选提交都会在 TerminusDB 留一个 `candidate-*` 分支，仓库分支会持续增长；
   建议增加候选分支的定期清理/回收策略（本轮验证已手动清理以恢复干净基线）。
4. **启动期端口复用竞态**：干净停止后启动稳定；若上一轮进程未完全释放端口，registry/email 可能 bind 失败退出。
   建议 start.ps1 在启动前对目标端口做占用探测/重试。

## 变更文件清单

- `research-wiki/src/llm_wiki/terminus_store.py`（缺陷 1、2）
- `research-wiki/src/llm_wiki/candidate_submission.py`（缺陷 2）
- `research-map/src/research_mapping/terminus_store.py`（缺陷 3）

合计 3 文件、+39 / -11 行。
