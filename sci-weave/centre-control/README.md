# 中央服务器

`centre-control` 只表示这些内容部署在中央服务器。下面每个目录都是独立项目，不共用锁文件，也不作为一个部署单元一起启动。

| 目录 | 是什么 |
| --- | --- |
| `research-map` | Research Mapping，同事已在实现 |
| `research-wiki` | LLM-Wiki，同事已在实现 |
| `buffer` | 中央草稿箱，尚未实现 |
| `centre-agents` | 中央协调 Agent，尚未实现 |
| `registery` | 主体与端侧 Agent 的登记表，尚未实现 |
| `web-ui` | 可视化网页，尚未实现 |
| `shared/audit-trail` | 中央留痕工具，接口层调用账本；多个中央项目共用的代码，不是独立部署单元 |

`shared/` 是**代码归属边界**，不是项目组：这里的代码被至少两个中央项目以 uv path 依赖引用，不产生组级 `pyproject.toml` 或组级 `uv.lock`，各调用方各自提交锁文件。

第三方服务容器（TerminusDB、Redpanda）不在这里，放在 `sci-weave/service/<服务名>/`：它们是本地验证用的独立服务，与中央业务项目分属不同的部署单元。
