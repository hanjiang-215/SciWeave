---
id: ai4-g1y7
status: closed
deps: []
links: []
created: 2026-10-27T11:33:39Z
type: chore
priority: 2
assignee: hanjiang
tags: [docs, dx, demo, centre-control]
---
# 中央控制面文档与演示可用性：README 缺项、规格状态过期、脚本提示与演示开关

四处在 2026-10-27 审查里发现的文档与演示期可用性问题，都是「代码已经对了，说明和提示还停在旧状态」：

1. **`sci-weave/centre-control/README.md` 表格缺三行**：`coordinator`、`email-service`、`shared/message-envelope` 都已交付，表里没有。新人按 README 读会以为中央控制面只有六个组件。
2. **`docs/superpowers/specs/2026-10-21-mapping-wiki-formalization-delivery-design.md` 状态仍是「待用户审阅」**，而它描述的 Mapping/Wiki 交付早已合并进 `develop`。10-22 的审查已提出，未改。
3. **`scripts/demo-dashboard.ps1` 收尾打印 `停止 : pwsh scripts/demo-dashboard.ps1 -Stop`**，而演示机上只有 Windows PowerShell 5.1，没有 `pwsh`。照抄会失败。
4. **`buffer/src/draft_buffer/main.py:98`**：`SCIWEAVE_BUFFER_DEMO=1` 时打印 `{status:ready}` 然后 `return 0`，不做任何服务。与 `ai4-c61f` 修掉的静默降级是同一形状：看起来启动成功，实际什么都不做。

## Acceptance Criteria

- [x] `centre-control/README.md` 的表覆盖实际存在的全部子项目，`coordinator`、`email-service`、`shared/message-envelope` 各有准确描述。
- [x] `2026-10-21-mapping-wiki-formalization-delivery-design.md` 的状态与「已实现并合并」一致。
- [x] `demo-dashboard.ps1` 的停止提示在只有 Windows PowerShell 的机器上可直接执行。
- [x] `SCIWEAVE_BUFFER_DEMO=1` 走演示短路时打印明确告警（说明该进程不提供服务），不再静默返回 0。


## Notes

**2026-10-27T12:00:38Z**

## 2026-10-27 修复

四项全部完成：

1. **`centre-control/README.md`** 补 `coordinator`（交接协调器）、`email-service`（人工通知投递）、`shared/message-envelope`（消息信封协议包）三行；message-envelope 那行注明「当前无生产调用方，接线决策见 `ai4-4bxp`」。
2. **规格状态**：`2026-10-21-mapping-wiki-formalization-delivery-design.md` 改为「已实现并合并进 `develop`」，核对 6 张下游票（`ai4-6s53`/`ai4-z0lb`/`ai4-1qyc`/`ai4-91tk`/`ai4-txhf`/`ai4-jdjx`）全部 closed。
3. **`demo-dashboard.ps1`**：停止提示改为运行时判断——有 `pwsh` 打印 pwsh，否则打印 `powershell scripts/demo-dashboard.ps1 -Stop`（本机实测生成 powershell 版本）；`.EXAMPLE` 同步换成可移植形式。
4. **buffer 演示开关**：`SCIWEAVE_BUFFER_DEMO=1` 现在输出 `{status:stub,serving:false,reason_code:buffer_demo_short_circuit,...}` 并向 stderr 打「不提供任何草稿箱服务」，不再静默输出 `ready` 后 return 0；新增 `tests/test_demo_short_circuit.py` 两条断言（status=stub、never ready、stderr 有告警）。

**验证**：buffer 全量 30 passed / 3 skipped（新增 2 条演示测试）；全量矩阵 21/21 阶段、863 项通过。另按本票 AC3 的需要实际验证了提示在无 pwsh 机器上可执行（见 Notes 内「生成提示」行——由 PowerShell 5.1 进程实测）。

AC4 的演示短路测试当时是在 Windows PowerShell 5.1 + uv 环境下跑的，输出 `2 passed`。
