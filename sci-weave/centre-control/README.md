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

第三方服务容器（TerminusDB、Redpanda）不在这里，放在 `sci-weave/service/<服务名>/`：它们是本地验证用的独立服务，与中央业务项目分属不同的部署单元。
