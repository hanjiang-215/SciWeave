---
id: ai4-c2t7
status: open
deps: [ai4-xup8]
links: []
created: 2026-10-20T06:31:26Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# Task Agent 初始化所需的 Mapping 查询契约

## Question

当 Mapping 开发完成并提供查询能力后，确定 Task Agent 初始化时读取 TaskNode、Task Owner、必要上游与配置版本所需的最小只读查询契约。该票只定义消费端需要的请求前置条件、响应字段、版本标识、空结果与不可用错误语义；不设计 Mapping 写入、运行期回调或领域 Buffer。

## Acceptance Criteria

确认由 Mapping 提供的最小只读初始化查询能力及其输入前置条件；明确 Task Agent 必需的 TaskNode、Task Owner、必要上游与配置版本字段；明确空结果、未授权、暂不可用和版本不兼容的错误语义；明确 Task Agent 仅在显式初始化时查询并持久化快照，运行期不依赖 Mapping 查询；不引入 Mapping 写入、领域 Buffer 或运行期回调。
