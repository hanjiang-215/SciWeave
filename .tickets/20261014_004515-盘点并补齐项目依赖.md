---
id: ai4-5vru
status: closed
deps: []
links: []
created: 2026-10-14T00:45:15Z
type: task
priority: 2
assignee: SciWeave
tags: [dependencies, setup]
---
# 盘点并补齐项目依赖

盘点 AI4Sci 当前运行时、开发工具、外部服务和文档依赖；确认技术栈后补齐缺失的包管理清单、锁文件、环境变量说明和验证命令。当前仓库没有源码或包管理文件，不能臆造具体运行时依赖。

## Acceptance Criteria

依赖分类和现状有可追溯记录；明确当前缺失项；技术栈确认后补齐对应依赖声明；保留凭据安全边界；完成验证并回写任务。

## Notes

**2026-10-14T01:18:29Z**

依赖盘点已完成并提交：92b97f0 docs(dependencies): document project dependency requirements。赛事文档目录整理提交为 0db1144，项目整体规则提交为 b333480；当前仍无源码和运行时包管理清单，具体运行时依赖待技术栈确定。验证：git diff --check 通过，工作区干净。

**2026-10-15T12:44:35Z**

补充依赖文档：记录 gitee-cli 用于 OpenI/Gitee 仓库协作和 Pull Request；当前环境执行 command -v gitee-cli 结果为未找到命令，因此版本、上游来源、许可证和安装方式待确认。文档验证：git diff --check 通过。

**2026-10-15T12:50:59Z**

提交 855774f 已通过 ssh_origin 推送到 feature/dev-a。尝试向 develop 创建 PR：gitee CLI auth status 显示未登录，OpenI 页面跳转 guest_verify，当前无法完成 PR 创建。

**2026-10-15T13:20:13Z**

更新 Gitee 协作配置：规则和依赖文档已记录 gitee-cli（命令名 gitee）创建目标为 develop 的 PR、origin/ssh_origin 的 Gitee 地址，以及 credential.helper store 配置和明文凭据风险。验证：gitee 0.7.1、gitee pr create --help、git config --get credential.helper=store、git diff --check 均通过。

**2026-10-15T13:29:06Z**

已创建 Gitee Pull Request #1，目标分支 develop，地址：https://gitee.com/OWNER/ai4science/pulls/1。分支 feature/dev-a 已通过 origin HTTPS 推送；ssh_origin 因权限不足失败，已记录并改用 credential.helper store。
