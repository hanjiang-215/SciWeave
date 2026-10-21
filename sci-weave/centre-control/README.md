# 中央服务器

`centre-control` 只表示这些内容部署在中央服务器。下面每个目录都是独立项目或第三方服务，不共用锁文件，也不作为一个部署单元一起启动。

| 目录 | 是什么 |
| --- | --- |
| `research-map` | Research Mapping，同事已在实现 |
| `research-wiki` | LLM-Wiki，同事已在实现 |
| `buffer` | 提交缓冲，尚未实现 |
| `centre-agents` | 中央协调 Agent，尚未实现 |
| `web-ui` | 可视化网页，尚未实现 |
| `message-queue` | 不写业务代码；消息队列使用旁边的 Redpanda |
| `terminusdb` | 图存储，第三方服务 |
| `redpanda` | 消息队列，第三方服务 |
