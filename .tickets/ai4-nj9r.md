---
id: ai4-nj9r
status: open
deps: []
links: [ai4-jfvy, ai4-fm4a]
created: 2026-10-28T00:24:02Z
type: feature
priority: 2
assignee: Frank Qi
tags: [toolkit, suite, packaging]
---
# 套件清单与 ZIP 打包：恢复 ai4-jfvy 推迟的 manifest 工作

`ai4-jfvy` 在 2026-10-19 把 Agent Kit manifest、Skills/Hooks 模板和多套件定制整体推迟。
这次做三个套件时只恢复了其中的**清单**部分（`suite.yaml` + `suitecheck`），打包与模板覆盖
仍是空白。

当前形态已经可用，但代价是「谁来切这个 zip」由人决定：

- 套件目录本身就是交付物，`install.sh` / `check.sh` 由安装它的 Agent 执行；
- 没有版本约束，没有「这个套件要求 Gateway ≥ x.y」，也没有覆盖规则；
- 打出来的 zip 会带上 `.env`（如果本地填过）和 `__pycache__`，全靠 `.gitignore` 挡。

## 差什么

1. **打包命令。** 一个 `suitecheck pack <suite>` 输出 `dist/<suite>-<version>.zip`，
   排除 `.env`、`__pycache__`、`.venv`、`*.pyc`、`.DS_Store`，并把清单摘要写进 zip 注释或
   一个 `MANIFEST.sha256`。
2. **版本兼容声明。** `requires.compat: {suitecheck: ">=0.1", harness: "fast-agent"}` 之类，
   让安装方在跑 `install.sh` 之前就能拒绝不兼容的套件。
3. **配置覆盖规则。** 平台模板与项目定制的边界：哪些键可以被本地覆盖，哪些一旦写了就不许改
   （令牌、能力上限）。`ai4-jfvy` 的 Question 原文就是这个，仍未回答。
4. **签名或摘要校验。** 至少让解压后的树能被核对成打包时那一棵。

## Acceptance Criteria

- [ ] `suitecheck pack` 打出的 zip 不含 `.env`、缓存与虚拟环境
- [ ] 打包前后 `suitecheck check` 都能通过（zip 内解压后同样通过）
- [ ] 清单能声明最低 `suitecheck` 版本，版本不足时 `check` 直接拒绝
- [ ] 覆盖规则写成文档并有一条校验：越过不可覆盖的键时报错
- [ ] `sci-weave/toolkits/README.md` 里的「上传一个 zip 给 Agent」有对应命令

## Notes

**2026-10-28T00:45:00Z**

先记录一个判断：**这三件事不该一起做。** 打包是机械的，覆盖规则是治理决策，
版本兼容需要先知道有哪些 harness。把它们塞进一张票会让最容易的那件被最难的那件拖住。

建议拆成三张：打包（本票保留）、配置覆盖规则（需要一次裁决，和 `ai4-jfvy` 的 Question 同源）、
版本兼容声明（等有第二个 harness 再说）。
