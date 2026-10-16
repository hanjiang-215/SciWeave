---
id: ai4-9f7i
status: closed
deps: []
links: []
created: 2026-10-16T00:38:11Z
type: grilling
priority: 0
assignee: qiyueran
parent: ai4-ru15
tags: [wayfinder:grilling, product, ai4science]
---
# 平台定位与用户边界

## Question
平台服务的基本对象和边界是什么？需要在宏观层面决定：服务单个科研人员、科研组、多个科研组还是开放生态；平台提供项目级协作还是跨项目资源网络；通用能力与示例科研场景如何区分。暂不讨论租户、账号或部署实现。

## Acceptance Criteria

明确目标用户、协作边界、平台定位和不包含的产品范围；为后续研究图、资源空间、治理和首版范围提供共同前提。

## Notes

**2026-10-16T01:44:01Z**

## Answer

平台服务对象确定为一个科研小组及其科研项目。小组采用一名管理员和若干成员的简单组织方式，当前不设计复杂权限、跨机构协作或开放生态。

平台边界确定为科研任务控制平面：负责初始科研路线图、路线图动态更新、任务节点、人员和 Agent 指派、结果汇聚、调度、审核、共享资源、执行留痕和审计；不针对具体学科或具体科研难题提供专业解决方案。

端侧 Agent 分为两类：研究人员可以通过 MCP、Skills、系统提示词和 Hooks 配置自己的 personal agent；平台只提供接入和协作接口。平台支持轻量、可配置的任务 Agent，但不开发新的通用智能体。

后续产品设计应围绕平台机制的通用性展开，而不是内置某个领域的科研能力。

**2026-10-16T01:48:06Z**

## Clarification

“不开发 Agent”明确指不开发新的通用 harness 框架，不代表平台不支持或不管理 Agent 能力配置。研究人员可以使用自己的 personal-agent harness，并通过 MCP、Skills、系统提示词和 Hooks 接入平台；平台提供的独立研究 Agent 使用轻量化、可配置的任务 harness。平台的开发重点仍是中央调度、审核、共享资源和执行留痕。
