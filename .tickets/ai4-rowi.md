---
id: ai4-rowi
status: closed
deps: []
links: []
created: 2026-10-19T06:47:28Z
type: epic
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# Agent Kit ZIP 交付与跨服务器验证边界

承接 Gateway 最小底座与 Agent Kit 交付地图；本票只解决一个实现前置决策，不直接编写产品代码。

## Design

## Question
面向其他服务器的 ZIP 交付包应包含哪些文件和元数据，如何安装、注入环境变量、校验版本并执行最小验证？需要明确源码/配置/运行时/持久化数据/真实凭据的边界，以及开发验证包和生产部署包是否分阶段。

## Acceptance Criteria

形成 ZIP 包内容清单、安装与升级边界、凭据排除规则、启动检查和跨服务器最小验收流程；结果可交给实现阶段制作可验证交付包。


## Notes

**2026-10-19T06:58:30Z**

2026-10-19：根据目标收敛，本阶段不实现 ZIP 交付和跨服务器部署验证，转入后续独立阶段。
