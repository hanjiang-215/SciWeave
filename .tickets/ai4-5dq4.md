---
id: ai4-5dq4
status: closed
deps: []
links: []
created: 2026-10-31T05:37:34Z
type: feature
priority: 2
assignee: Frank Qi
tags: [toolkit, release]
---
# 套件发版工具入库与发版技能

sci-weave/toolkits/release-scripts/ 下的五个发版脚本（pack/publish/release/install-suite 与 README）目前只存在于本地工作区，从未入库；同时缺少一个给 Agent 用的发版技能，每次发版仍要人工回忆步骤与前置条件。

## Acceptance Criteria

- [x] 五个脚本入库并可执行（shell 语法检查通过）。
- [x] 新增发版技能在 .cursor/skills 与 .dsh/skills 两处可用。
- [x] 设计规格写入 docs/superpowers/specs/ 并说明 .dsh 为派生副本。

## Notes

实现（2026-10-31，feature/frank-qi）：

- 脚本入库到 `sci-weave/toolkits/release-scripts/`，权限整理为脚本 `755`、README `644`；四个脚本 `sh -n` 全部通过。
- `pack.sh` 实跑出包：`sciweave-po-toolkit-0.1.0.zip`（36K）、`sciweave-researcher-toolkit-0.1.0.zip`（608K）与 `SHA256SUMS`。
- `publish.sh v9.9.9` 按设计拒绝：`refuse: publish version v9.9.9 does not match suite.yaml (0.1.0)`。
- 技能 `suite-release` 落在 `.cursor/skills/engineering/suite-release/`（事实源），同步到 `.dsh/skills/engineering/suite-release/`（派生副本，`.gitignore` 忽略，不入库）；两处 `diff -r` 无差异。
- 规格：`docs/superpowers/specs/2026-10-31-suite-release-tooling-design.md`，§4.1 写明两处位置与 `.dsh/` 不入库的理由。
- 工单索引：`ticket_index.py check` → `OK：298 张工单，7 个模块，生成文件一致。`
- `CHANGELOG.md` 本次未重生成：现在跑 `git cliff` 会把未合入 `develop` 的其他分支提交写进 unreleased，留到发版时常规重生成。

PR：https://gitee.com/qi-yueran/ai4science/pulls/70 （feature/frank-qi → develop）

未验证：真实发一次的端到端（会真的推 tag、建 release），留给下一次实际发版。

